#include "util/strings.h"

/* Prints a count. */
int main(void) {
    struct counted c;
    c.length = demo_count("codemap");
    return c.length;
}
