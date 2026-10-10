# Batch-Find-Replace
Do a find and replace on many types of fimd types and files
1. Browse to a folder. Enable Include subfolders for recursive scanning;
   turn it off to scan only files directly in that folder.
2. File patterns use semicolons: *.html;*.htm;*.css;*.js;*.txt
   Use * for all filenames. Images, executables, archives and binary-looking
   files are skipped. Backups and symbolic links are always skipped.
3. Enter Find and Replace text. Empty Replace deletes matching text.
   Both boxes accept multiple lines. Use actual newlines for literal searches.
4. Preview first. The file list shows matches and encoding. Select a file
   to see its proposed changes (up to the first 300 diff lines).
5. Replace selected files or all preview results. A confirmation reports
   exactly how many files and matches are included. Modified files since the
   preview are skipped; run Preview again to refresh.

OPTIONS
• Match case: distinguish ABC from abc.
• Whole words: word boundaries around the search expression.
• Regular expression: Python regex syntax. Replacement accepts backreferences
  such as \\1 or \\g<name>. Literal mode treats backslashes literally.
• Encoding: Auto uses BOM detection or strict UTF-8. For older files select
  cp1252 or latin-1 explicitly. Incorrect/unsupported encodings are skipped.
• Maximum size: skips large files (default 10 MB).
• Excluded folders: semicolon-separated folder names or wildcard patterns.

SAFETY AND BACKUPS
Preview does not change files. Every changed file receives a unique adjacent
backup named ORIGINAL.bfr-backup-TIMESTAMP-IDENTIFIER. Backup creation must
succeed before a replacement is written. Original newline characters and
encoding are preserved. Writes use a temporary file in the same directory.
To restore, close programs using the original and copy its backup over it.
Cancel stops between files; replacements already completed remain completed.
The run log records successful changes and any errors. You can save it.

HTML AND OTHER FILES
This edits text in files; it does not translate languages automatically and
it does not rename files. Replacing HTML, CSS or JavaScript can affect behavior,
so inspect the preview. Word/PDF/image files are not supported text formats.
On Linux, use a locally mounted Samba share, not an smb:// address. Windows
UNC paths work when your account has access. Do not edit files concurrently.

INSTALL
Windows: install Python with Tkinter, then run this file using Python.
MX Linux: if Tkinter is missing, install python3-tk using your package manager.
No pip packages are required.
'''
