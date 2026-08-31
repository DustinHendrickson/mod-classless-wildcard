/*
 * mpqtool — minimal MPQ pack/extract/list utility for the
 * mod-classless-wildcard client patch. Links against StormLib.
 *
 * Usage:
 *   mpqtool create  <archive.mpq> <diskfile@mpqpath> [more files...]
 *   mpqtool extract <archive.mpq> <mpqpath> <outfile>
 *   mpqtool list    <archive.mpq>
 *
 * Example (build the Hero class patch):
 *   mpqtool create patch-4.MPQ ChrClasses_hero.dbc@DBFilesClient\\ChrClasses.dbc
 */

#define __STORMLIB_NO_AUTO_LINK__
#include <StormLib.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int pack(int argc, char** argv)
{
    const char* archiveName = argv[0];
    HANDLE hMpq = NULL;

    if (!SFileCreateArchive(archiveName, MPQ_CREATE_LISTFILE | MPQ_CREATE_ATTRIBUTES,
                            (DWORD)(argc + 8), &hMpq))
    {
        fprintf(stderr, "error: cannot create %s (err %u)\n", archiveName, SErrGetLastError());
        return 1;
    }

    for (int i = 1; i < argc; ++i)
    {
        char spec[1024];
        strncpy(spec, argv[i], sizeof(spec) - 1);
        spec[sizeof(spec) - 1] = 0;

        char* at = strchr(spec, '@');
        const char* diskPath = spec;
        const char* mpqPath = spec;
        if (at)
        {
            *at = 0;
            mpqPath = at + 1;
        }

        if (!SFileAddFileEx(hMpq, diskPath, mpqPath,
                            MPQ_FILE_COMPRESS | MPQ_FILE_REPLACEEXISTING,
                            MPQ_COMPRESSION_ZLIB, MPQ_COMPRESSION_ZLIB))
        {
            fprintf(stderr, "error: cannot add %s as %s (err %u)\n", diskPath, mpqPath, SErrGetLastError());
            SFileCloseArchive(hMpq);
            return 1;
        }
        printf("added %s -> %s\n", diskPath, mpqPath);
    }

    SFileCloseArchive(hMpq);
    printf("created %s\n", archiveName);
    return 0;
}

static int extract(const char* archiveName, const char* mpqPath, const char* outPath)
{
    HANDLE hMpq = NULL, hFile = NULL;
    if (!SFileOpenArchive(archiveName, 0, MPQ_OPEN_READ_ONLY, &hMpq))
    {
        fprintf(stderr, "error: cannot open %s (err %u)\n", archiveName, SErrGetLastError());
        return 1;
    }
    if (!SFileOpenFileEx(hMpq, mpqPath, 0, &hFile))
    {
        fprintf(stderr, "error: %s not found in archive (err %u)\n", mpqPath, SErrGetLastError());
        SFileCloseArchive(hMpq);
        return 1;
    }

    FILE* out = fopen(outPath, "wb");
    if (!out)
    {
        fprintf(stderr, "error: cannot write %s\n", outPath);
        SFileCloseFile(hFile);
        SFileCloseArchive(hMpq);
        return 1;
    }

    char buffer[0x10000];
    for (;;)
    {
        DWORD read = 0;
        bool ok = SFileReadFile(hFile, buffer, sizeof(buffer), &read, NULL);
        if (read > 0)
            fwrite(buffer, 1, read, out);
        if (!ok || read < sizeof(buffer))
            break; /* EOF (partial or empty read) */
    }

    fclose(out);
    SFileCloseFile(hFile);
    SFileCloseArchive(hMpq);
    printf("extracted %s -> %s\n", mpqPath, outPath);
    return 0;
}

static int list(const char* archiveName)
{
    HANDLE hMpq = NULL;
    SFILE_FIND_DATA fd;
    if (!SFileOpenArchive(archiveName, 0, MPQ_OPEN_READ_ONLY, &hMpq))
    {
        fprintf(stderr, "error: cannot open %s (err %u)\n", archiveName, SErrGetLastError());
        return 1;
    }
    HANDLE hFind = SFileFindFirstFile(hMpq, "*", &fd, NULL);
    if (hFind)
    {
        do
        {
            printf("%10u  %s\n", fd.dwFileSize, fd.cFileName);
        } while (SFileFindNextFile(hFind, &fd));
        SFileFindClose(hFind);
    }
    SFileCloseArchive(hMpq);
    return 0;
}

int main(int argc, char** argv)
{
    if (argc >= 4 && !strcmp(argv[1], "create"))
        return pack(argc - 2, argv + 2);
    if (argc == 5 && !strcmp(argv[1], "extract"))
        return extract(argv[2], argv[3], argv[4]);
    if (argc == 3 && !strcmp(argv[1], "list"))
        return list(argv[2]);

    fprintf(stderr,
        "usage:\n"
        "  mpqtool create  <archive.mpq> <diskfile@mpqpath> [...]\n"
        "  mpqtool extract <archive.mpq> <mpqpath> <outfile>\n"
        "  mpqtool list    <archive.mpq>\n");
    return 2;
}
