/*
 * fbgray - copia cuadros en escala de grises desde stdin al framebuffer.
 *
 * Lee cuadros de 720x576 a 8 bits por pixel (luma pura, tal como sale de
 * ffmpeg con -vf extractplanes=y -f rawvideo) y los escribe en /dev/fb0
 * expandiendo R=G=B a 32 o 16 bpp. Por defecto estira la luma de rango de
 * video (16-235) a rango pleno (0-255); con -r la copia sin cambios.
 *
 * Existe porque en la Pi Zero pasar cuadros de 32 bits por la tuberia desde
 * ffmpeg (41 MB/s) no llega a tiempo real (14 fps); con 8 bits por pixel
 * (10 MB/s) sobra (49 fps), y la expansion en C es casi gratis.
 *
 * Cada fila se arma en memoria normal y se copia con memcpy: escribir pixel
 * por pixel sobre el framebuffer (memoria sin cache) cuesta mucho mas.
 *
 * Compilar: gcc -O2 -o fbgray fbgray.c
 */

#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define ANCHO 720
#define ALTO 576

static uint8_t gris[ANCHO * ALTO];

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

int main(int argc, char **argv)
{
    int rango_video = !(argc > 1 && strcmp(argv[1], "-r") == 0);
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

    static uint32_t fila32[ANCHO];
    static uint16_t fila16[ANCHO];

    while (leer_cuadro(gris, sizeof gris)) {
        for (int y = 0; y < ALTO; y++) {
            const uint8_t *src = gris + y * ANCHO;
            uint8_t *fila = fb + (size_t)y * fix.line_length;
            if (var.bits_per_pixel == 32) {
                for (int x = 0; x < ANCHO; x++)
                    fila32[x] = lut32[src[x]];
                memcpy(fila, fila32, sizeof fila32);
            } else {
                for (int x = 0; x < ANCHO; x++)
                    fila16[x] = lut16[src[x]];
                memcpy(fila, fila16, sizeof fila16);
            }
        }
    }
    return 0;
}
