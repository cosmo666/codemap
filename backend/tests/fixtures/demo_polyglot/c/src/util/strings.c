#include "strings.h"

/* Counts bytes until NUL. */
int demo_count(const char *text) {
    int n = 0;
    while (text[n] != '\0') {
        n = n + 1;
    }
    return n;
}
