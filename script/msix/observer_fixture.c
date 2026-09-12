/* Copyright 2026 Trieflow LLC. MIT. Diagnostic test only, never packaged. */
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void caught(int sig) {
    fprintf(stderr, "fixture handled signal %d\n", sig);
    exit(1);
}

__attribute__((noinline)) static void observer_fault_leaf(void) {
    volatile int *missing = (volatile int *)0;
    *missing = 7;
}

int main(int argc, char **argv) {
    signal(SIGSEGV, caught);
    puts("fixture ready");
    fflush(stdout);
    if (getchar() == EOF) return 2;
    if (argc == 2 && strcmp(argv[1], "fault") == 0) observer_fault_leaf();
    puts("fixture normal exit");
    return 0;
}
