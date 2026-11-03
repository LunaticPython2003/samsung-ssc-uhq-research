/*
 * Isolated Samsung SSC ARM64 encoder probe.
 * Research only: output is NOT a validated A2DP packet.
 * Compile on the Android device with Termux clang, using dlopen on device.
 * No Android settings, Bluetooth stack, or firmware modifications.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
#include <math.h>
#include <inttypes.h>
#include <dlfcn.h>
#include <unistd.h>

typedef int (*get_size_t)(int, int);
typedef void* (*create_t)(int, int, int, int*);
typedef void (*destroy_t)(void*);
typedef int (*encode_t)(void*, int32_t*, int, uint8_t*, int);
typedef void (*uhq_info_t)(int, int*, int*);

static int parse_i(const char *s, int *out) {
    char *end = NULL;
    long n = strtol(s, &end, 10);
    if (!s[0] || *end || n < 0 || n > 2000000) return 0;
    *out = (int)n;
    return 1;
}
static void *symbol(void *handle, const char *name) {
    dlerror();
    void *s = dlsym(handle, name);
    const char *err = dlerror();
    if (err || !s) {
        fprintf(stderr, "missing symbol %s: %s\n", name, err ? err : "null");
        exit(3);
    }
    return s;
}
static size_t changed_bytes(const uint8_t *p, size_t len, size_t *last) {
    size_t count = 0;
    *last = 0;
    for (size_t i=0; i<len; ++i) if (p[i] != 0xA5) {
        ++count;
        *last = i+1;
    }
    return count;
}
int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s info [rate channels bit_depth]\n"
                        "       %s encode rate channels bit_depth bitrate frame_samples frames [output.raw]\n", argv[0], argv[0]);
        return 2;
    }
    int encode = !strcmp(argv[1],"encode");
    if (!encode && strcmp(argv[1],"info")) return 2;
    int rate=48000, channels=2, depth=24, bitrate=328000, samples=864, frames=1;
    if ((encode && argc < 8) || (!encode && argc != 2 && argc != 5)) return 2;
    if (argc >= 5 && (!parse_i(argv[2],&rate) ||
                      !parse_i(argv[3],&channels) ||
                      !parse_i(argv[4],&depth))) return 2;
    if (encode && (!parse_i(argv[5],&bitrate) ||
                   !parse_i(argv[6],&samples) ||
                   !parse_i(argv[7],&frames))) return 2;
    if ((rate!=44100 && rate!=48000 && rate!=96000) ||
        channels != 2 || (depth!=16 && depth!=24) ||
        samples<16 || samples>1024 || frames<1 || frames>32)
    {
        fprintf(stderr,"unsupported or unsafe probe args\n"); return 2;
    }
    /* A library's global DRC state means this is intentionally single-threaded. */
    const char *libname="/system/lib64/libScalable_Encoder.so";
    void *lib=dlopen(libname, RTLD_NOW | RTLD_LOCAL);
    if (!lib) { fprintf(stderr,"dlopen(%s): %s\n",libname,dlerror()); return 3; }
    get_size_t get_size=(get_size_t)symbol(lib,"ssc_encoder_get_size");
    create_t create=(create_t)symbol(lib,"ssc_encoder_create");
    destroy_t destroy=(destroy_t)symbol(lib,"ssc_encoder_destroy");
    encode_t ssc_encode=(encode_t)symbol(lib,"ssc_encode");
    uhq_info_t uhq_info=(uhq_info_t)symbol(lib,"get_uhq_info_from_bitrate");
    int err = -12345;
    int bytes=get_size(channels,rate);
    fprintf(stderr,"probe: mode=%s rate=%d ch=%d depth=%d context_bytes=%d\n",
            encode?"encode":"info", rate,channels,depth,bytes);
    if (bytes<256 || bytes>2000000) {
        fprintf(stderr,"implausible context size; refusing to call create\n"); return 4;
    }
    int flag_a=-9999,flag_b=-9999;
    uhq_info(bitrate, &flag_a, &flag_b);
    fprintf(stderr,"bitrate=%d uhq_selector=(%d,%d) [NOT documented meaning]\n",
            bitrate,flag_a,flag_b);
    void *ctx=create(rate,channels,depth,&err);
    fprintf(stderr,"create=%p status=%d\n",ctx,err);
    if (!ctx || err != 0) {
        if(ctx) destroy(ctx);
        dlclose(lib);
        return 5;
    }
    if (!encode) { destroy(ctx); dlclose(lib); return 0; }
    const size_t pcm_n=(size_t)samples*(size_t)channels;
    int32_t *pcm=calloc(pcm_n+64,sizeof(*pcm));
    const size_t out_cap=16384;
    uint8_t *out=malloc(out_cap+128);
    FILE *f=NULL;
    if (!pcm || !out) { fprintf(stderr,"allocation failed\n");return 6; }
    if(argc>8) {
        f=fopen(argv[8],"wb");
        if (!f) { perror("fopen"); return 6; }
    }
    for(int frame=0; frame<frames; ++frame) {
        /* Interleaved signed PCM32; low amplitude, no source music. */
        for (int i=0;i<samples;i++) {
            double phase=2.0*3.14159265358979323846*440.0*(i+frame*samples)/(double)rate;
            int32_t v=(int32_t)(sin(phase)*2000000.0);
            for (int ch=0;ch<channels;ch++) pcm[i*channels+ch]=v;
        }
        memset(out,0xA5,out_cap+128);
        /* Return type is *hypothetical* until its AArch64 call site is inspected. */
        int result=ssc_encode(ctx,pcm,samples,out,bitrate);
        size_t last=0;
        size_t modified=changed_bytes(out,out_cap,&last);
        int canary_ok=1;
        for(size_t k=out_cap;k<out_cap+128;k++) if(out[k]!=0xA5) canary_ok=0;
        fprintf(stderr,"frame=%d result_register=%d changed=%zu last_modified_exclusive=%zu canary=%s prefix=",
                frame,result,modified,last,canary_ok?"OK":"CORRUPTED");
        for(size_t j=0;j<32 && j<last;j++) fprintf(stderr,"%02x",out[j]);
        fprintf(stderr,"\n");
        if(!canary_ok || !modified) {
            fprintf(stderr,"invalid output; aborting\n");
            if(f) fclose(f);
            destroy(ctx);
            dlclose(lib);
            return 7;
        }
        if(f) {
            /*
             * Unverified byte count: prefer plausible return register if within
             * output bounds; otherwise use last changed byte, which is only a
             * lower-bound estimate, not a frame format contract.
             */
            size_t emitted=(result>=4 && result<=4096) ? (size_t)result : last;
            if (emitted > out_cap) emitted = out_cap;
            fwrite(out,1,emitted,f);
        }
    }
    if(f) fclose(f);
    free(pcm);free(out);
    destroy(ctx);
    dlclose(lib);
    return 0;
}
