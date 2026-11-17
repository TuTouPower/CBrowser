#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XShm.h>

static int g_x_error_code = 0;
static int g_x_request_code = 0;
static int g_x_minor_code = 0;

static int handle_x_error(Display *dpy, XErrorEvent *e) {
    g_x_error_code = e->error_code;
    g_x_request_code = e->request_code;
    g_x_minor_code = e->minor_code;
    return 0;
}

int main(int argc, char **argv) {
    int expect_failure = 0;
    if (argc > 1 && strcmp(argv[1], "--expect-shm-denied") == 0) {
        expect_failure = 1;
    }

    char *display_name = getenv("DISPLAY");
    if (!display_name) display_name = ":99";

    Display *dpy = XOpenDisplay(display_name);
    if (!dpy) {
        fprintf(stderr, "FAIL: Cannot open display %s\n", display_name);
        return 10;
    }

    // Set custom error handler to catch X errors synchronously
    XSetErrorHandler(handle_x_error);

    if (!XShmQueryExtension(dpy)) {
        fprintf(stderr, "FAIL: XShm extension not supported on display %s\n", display_name);
        XCloseDisplay(dpy);
        return 11;
    }

    int major, minor;
    Bool pixmaps;
    if (!XShmQueryVersion(dpy, &major, &minor, &pixmaps)) {
        fprintf(stderr, "FAIL: XShmQueryVersion failed\n");
        XCloseDisplay(dpy);
        return 12;
    }
    printf("INFO: XShm extension active (version %d.%d, pixmaps=%d)\n", major, minor, pixmaps);

    int screen = DefaultScreen(dpy);
    Window root = RootWindow(dpy, screen);
    XWindowAttributes wa;
    XGetWindowAttributes(dpy, root, &wa);

    XShmSegmentInfo shminfo;
    memset(&shminfo, 0, sizeof(shminfo));
    XImage *img = XShmCreateImage(dpy, wa.visual, wa.depth, ZPixmap, NULL, &shminfo, 100, 100);
    if (!img) {
        fprintf(stderr, "FAIL: XShmCreateImage failed\n");
        XCloseDisplay(dpy);
        return 13;
    }

    shminfo.shmid = shmget(IPC_PRIVATE, img->bytes_per_line * img->height, IPC_CREAT | 0777);
    if (shminfo.shmid < 0) {
        perror("FAIL: shmget failed");
        XDestroyImage(img);
        XCloseDisplay(dpy);
        return 14;
    }

    shminfo.shmaddr = img->data = (char *)shmat(shminfo.shmid, 0, 0);
    if (shminfo.shmaddr == (char *)-1) {
        perror("FAIL: shmat failed");
        shmctl(shminfo.shmid, IPC_RMID, 0);
        XDestroyImage(img);
        XCloseDisplay(dpy);
        return 15;
    }
    shminfo.readOnly = False;

    g_x_error_code = 0;
    XShmAttach(dpy, &shminfo);
    XSync(dpy, False); // Sync to ensure X server processed XShmAttach

    if (g_x_error_code != 0) {
        shmdt(shminfo.shmaddr);
        shmctl(shminfo.shmid, IPC_RMID, 0);
        XDestroyImage(img);
        XCloseDisplay(dpy);

        if (expect_failure) {
            if (g_x_error_code == BadAccess) {
                printf("CONFIRMED_SHM_DENIED: XShmAttach rejected with BadAccess (error=%d). Isolation verified.\n", g_x_error_code);
                return 0; // Negative test passed
            } else {
                fprintf(stderr, "FAIL: Expected BadAccess (%d), but got X error code %d\n", BadAccess, g_x_error_code);
                return 20;
            }
        } else {
            fprintf(stderr, "FAIL: Unexpected X error during XShmAttach: %d\n", g_x_error_code);
            return 21;
        }
    }

    // Attempt XShmGetImage
    g_x_error_code = 0;
    Status get_s = XShmGetImage(dpy, root, img, 0, 0, AllPlanes);
    XSync(dpy, False);

    if (g_x_error_code != 0 || get_s == 0) {
        // Both the client and server had a segment id, but X server failed to access it in its IPC namespace!
        XShmDetach(dpy, &shminfo);
        XSync(dpy, False);
        shmdt(shminfo.shmaddr);
        shmctl(shminfo.shmid, IPC_RMID, 0);
        XDestroyImage(img);
        XCloseDisplay(dpy);

        if (expect_failure) {
            printf("CONFIRMED_SHM_DENIED: XShmGetImage failed (status=%d, x_err=%d) due to cross-IPC memory isolation.\n", get_s, g_x_error_code);
            return 0; // Negative test passed
        } else {
            fprintf(stderr, "FAIL: XShmGetImage failed unexpectedly (status=%d, x_err=%d)\n", get_s, g_x_error_code);
            return 30;
        }
    }

    if (expect_failure) {
        fprintf(stderr, "FAIL: Expected XShm operation to fail, but XShmGetImage succeeded across IPC boundaries!\n");
        XShmDetach(dpy, &shminfo);
        XSync(dpy, False);
        shmdt(shminfo.shmaddr);
        shmctl(shminfo.shmid, IPC_RMID, 0);
        XDestroyImage(img);
        XCloseDisplay(dpy);
        return 22;
    }

    printf("PASS: XShmGetImage succeeded! Sample pixel=(%02x, %02x, %02x)\n",
           (unsigned char)img->data[0], (unsigned char)img->data[1], (unsigned char)img->data[2]);

    XShmDetach(dpy, &shminfo);
    XSync(dpy, False);
    shmdt(shminfo.shmaddr);
    shmctl(shminfo.shmid, IPC_RMID, 0);
    XDestroyImage(img);
    XCloseDisplay(dpy);

    printf("PASS: Positive MIT-SHM verification completed successfully.\n");
    return 0;
}
