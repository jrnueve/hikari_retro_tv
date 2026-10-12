/*
 * fbgray - copia cuadros en escala de grises desde stdin al framebuffer.
 *
 * Lee cuadros de luma pura a 8 bits por pixel, en el tamano nativo del
 * canal (tal como sale de ffmpeg con -vf extractplanes=y -f rawvideo), y los
 * escribe en /dev/fb0 (720x576) expandiendo R=G=B a 32 o 16 bpp. Por defecto
 * estira la luma de rango de video (16-235) a rango pleno (0-255); con -r la
 * copia sin cambios.
 *
 * Existe porque en la Pi Zero pasar cuadros de 32 bits por la tuberia desde
 * ffmpeg (41 MB/s) no llega a tiempo real (14 fps); con 8 bits por pixel
 * (10 MB/s) sobra (49 fps), y la expansion en C es casi gratis.
 *
 * Tamano: ffmpeg no escala nada. Escalar con swscale satura la Pi (medido:
 * 82 % -> 100 % de CPU para poner bandas a un 16:9). fbgray lleva el cuadro
 * de entrada a un rectangulo activo eligiendo, para cada pixel de salida, el
 * pixel de entrada mas cercano (tablas precalculadas: cuesta lo mismo que
 * copiar), y pinta negro alrededor. Asi un 16:9 queda con bandas, un 640x360
 * llena el ancho y un 720x480 ocupa las 576 lineas, sin costo extra.
 *
 * El tamano de entrada y el rectangulo activo salen de un archivo (-v) que
 * escribe hikaritvd cuando ffmpeg describe el video, lo que pasa antes del
 * primer cuadro. Formato: "ancho alto ancho_activo alto_activo". fbgray
 * espera a que haya datos en stdin, y recien ahi lee el archivo (hasta 3 s;
 * si no aparece, asume 720x576 a pantalla completa). Despues lo relee una
 * vez por segundo, por si cambia el rectangulo activo; el tamano de entrada
 * no puede cambiar sin reiniciar el pipeline.
 *
 * Cada fila se arma en memoria normal y se copia con memcpy: escribir pixel
 * por pixel sobre el framebuffer (memoria sin cache) cuesta mucho mas.
 *
 * Al escribir el primer cuadro avisa por stderr ("fbgray: primer cuadro"):
 * hikaritvd lo usa para saber cuando el canal ya esta en pantalla.
 *
 * Uso:      fbgray [-r] [-v ARCHIVO_VIDEO]
 * Compilar: gcc -O2 -o fbgray fbgray.c
 */

#include <fcntl.h>
#include <linux/fb.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define ANCHO 720
#define ALTO 576
#define MAX_ANCHO 1920
#define MAX_ALTO 1088

static uint8_t gris[MAX_ANCHO * MAX_ALTO];

struct video {
    int ancho, alto;            /* cuadro de entrada */
    int act_ancho, act_alto;    /* rectangulo activo en pantalla */
};

static int leer_cuadro(uint8_t *p, size_t n)
{
    while (n > 0) {
        ssize_t r = read(0, p, n);
        if (r <= 0)
            return 0;
        p += r;
        n -= (size_t)r;
    }
    return 1;
}

/* Lee el archivo de video si cambio desde la ultima vez. 1 si lo leyo. */
static int leer_video(const char *ruta, struct timespec *visto,
                      struct video *v)
{
    struct stat st;
    if (!ruta || stat(ruta, &st) < 0)
        return 0;
    if (st.st_mtim.tv_sec == visto->tv_sec &&
        st.st_mtim.tv_nsec == visto->tv_nsec)
        return 0;
    FILE *f = fopen(ruta, "r");
    if (!f)
        return 0;
    struct video n;
    int ok = fscanf(f, "%d %d %d %d", &n.ancho, &n.alto,
                    &n.act_ancho, &n.act_alto) == 4;
    fclose(f);
    if (!ok || n.ancho < 2 || n.ancho > MAX_ANCHO || n.alto < 2 ||
        n.alto > MAX_ALTO || n.act_ancho < 2 || n.act_ancho > ANCHO ||
        n.act_alto < 2 || n.act_alto > ALTO)
        return 0;
    *visto = st.st_mtim;
    *v = n;
    return 1;
}

int main(int argc, char **argv)
{
    int rango_video = 1, opt;
    const char *archivo = NULL;
    while ((opt = getopt(argc, argv, "rv:")) != -1) {
        if (opt == 'r')
            rango_video = 0;
        else if (opt == 'v')
            archivo = optarg;
        else {
            fprintf(stderr, "uso: fbgray [-r] [-v archivo_video]\n");
            return 2;
        }
    }

    struct fb_var_screeninfo var;
    struct fb_fix_screeninfo fix;
    int fd = open("/dev/fb0", O_RDWR);

    if (fd < 0) {
        perror("/dev/fb0");
        return 1;
    }
    if (ioctl(fd, FBIOGET_VSCREENINFO, &var) < 0 ||
        ioctl(fd, FBIOGET_FSCREENINFO, &fix) < 0) {
        perror("ioctl fb");
        return 1;
    }
    if (var.xres != ANCHO || var.yres != ALTO ||
        (var.bits_per_pixel != 32 && var.bits_per_pixel != 16)) {
        fprintf(stderr, "fbgray: fb %ux%u %ubpp no soportado\n",
                var.xres, var.yres, var.bits_per_pixel);
        return 1;
    }

    uint8_t *fb = mmap(NULL, fix.smem_len, PROT_READ | PROT_WRITE,
                       MAP_SHARED, fd, 0);
    if (fb == MAP_FAILED) {
        perror("mmap fb");
        return 1;
    }

    uint32_t lut32[256];
    uint16_t lut16[256];
    for (int i = 0; i < 256; i++) {
        int v = i;
        if (rango_video) {
            v = (i - 16) * 255 / 219;
            v = v < 0 ? 0 : (v > 255 ? 255 : v);
        }
        lut32[i] = (uint32_t)v * 0x010101u;
        lut16[i] = (uint16_t)(((v >> 3) << 11) | ((v >> 2) << 5) | (v >> 3));
    }

    /* Esperar el primer dato: para entonces ffmpeg ya describio el video y
     * hikaritvd escribio el archivo (o esta por hacerlo). */
    struct pollfd pfd = {.fd = 0, .events = POLLIN};
    while (poll(&pfd, 1, -1) < 0)
        ;
    struct video v = {ANCHO, ALTO, ANCHO, ALTO};
    struct timespec visto = {0, 0};
    for (int i = 0; i < 60 && !leer_video(archivo, &visto, &v); i++) {
        struct timespec t = {0, 50 * 1000000L};
        nanosleep(&t, NULL);
    }
    const int ancho = v.ancho, alto = v.alto;   /* fijos para el pipeline */
    const size_t n_entrada = (size_t)ancho * alto;

    static uint32_t fila32[ANCHO];
    static uint16_t fila16[ANCHO];
    static int col[ANCHO];          /* columna de entrada de cada salida */
    const size_t bpp = var.bits_per_pixel / 8;
    int recalcular = 1;
    int izq = 0, arriba = 0;
    long cuadros = 0;

    while (leer_cuadro(gris, n_entrada)) {
        if (cuadros % 25 == 0 && cuadros > 0) {
            struct video n = v;
            if (leer_video(archivo, &visto, &n) &&
                (n.act_ancho != v.act_ancho || n.act_alto != v.act_alto)) {
                v.act_ancho = n.act_ancho;
                v.act_alto = n.act_alto;
                recalcular = 1;
            }
        }
        if (recalcular) {
            /* Tabla de columnas y negro fuera del rectangulo activo */
            izq = (ANCHO - v.act_ancho) / 2;
            arriba = (ALTO - v.act_alto) / 2;
            for (int x = 0; x < v.act_ancho; x++)
                col[x] = x * ancho / v.act_ancho;
            for (int y = 0; y < ALTO; y++) {
                uint8_t *fila = fb + (size_t)y * fix.line_length;
                if (y < arriba || y >= arriba + v.act_alto) {
                    memset(fila, 0, ANCHO * bpp);
                } else {
                    memset(fila, 0, izq * bpp);
                    memset(fila + (izq + v.act_ancho) * bpp, 0,
                           (ANCHO - izq - v.act_ancho) * bpp);
                }
            }
            recalcular = 0;
        }
        const int identidad = (ancho == v.act_ancho);
        for (int y = 0; y < v.act_alto; y++) {
            const uint8_t *src = gris + (size_t)(y * alto / v.act_alto) * ancho;
            uint8_t *fila = fb + (size_t)(arriba + y) * fix.line_length
                            + izq * bpp;
            if (bpp == 4) {
                if (identidad)
                    for (int x = 0; x < v.act_ancho; x++)
                        fila32[x] = lut32[src[x]];
                else
                    for (int x = 0; x < v.act_ancho; x++)
                        fila32[x] = lut32[src[col[x]]];
                memcpy(fila, fila32, v.act_ancho * 4);
            } else {
                if (identidad)
                    for (int x = 0; x < v.act_ancho; x++)
                        fila16[x] = lut16[src[x]];
                else
                    for (int x = 0; x < v.act_ancho; x++)
                        fila16[x] = lut16[src[col[x]]];
                memcpy(fila, fila16, v.act_ancho * 2);
            }
        }
        /* hikaritvd espera esta linea para saber que el canal ya se ve */
        if (cuadros++ == 0)
            fputs("fbgray: primer cuadro\n", stderr);
    }
    return 0;
}
