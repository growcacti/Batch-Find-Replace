#!/usr/bin/env python3
"""Batch Find and Replace — Python 3.9+, standard library only.
Run: python3 batch_find_replace.py
Use Help inside the program for instructions.
"""
import codecs
import difflib
import fnmatch
import hashlib
import os
from pathlib import Path
import queue
import re
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

HELP = '''BATCH FIND AND REPLACE

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

BINARY_EXT = {'.png','.jpg','.jpeg','.gif','.webp','.ico','.pdf','.zip','.gz',
              '.tar','.7z','.exe','.dll','.so','.bin','.mp3','.mp4','.avi',
              '.woff','.woff2','.ttf','.doc','.docx','.xlsx','.pyc','.sqlite3'}

def decode_bytes(data, requested='Auto'):
    if requested == 'Auto':
        for bom, encoding in [(codecs.BOM_UTF32_LE,'utf-32'),
                              (codecs.BOM_UTF32_BE,'utf-32'),
                              (codecs.BOM_UTF8,'utf-8-sig'),
                              (codecs.BOM_UTF16_LE,'utf-16'),
                              (codecs.BOM_UTF16_BE,'utf-16')]:
            if data.startswith(bom):
                text = data.decode(encoding)
                # Explicit endianness keeps the original BOM when re-encoding.
                if encoding in ('utf-16','utf-32'):
                    endian = 'le' if bom in (codecs.BOM_UTF16_LE,codecs.BOM_UTF32_LE) else 'be'
                    actual = encoding + '-' + endian
                    return data.decode(actual), actual
                return text, encoding
        requested = 'utf-8'
    text = data.decode(requested, errors='strict')
    if any(ord(c) < 32 and c not in '\t\n\r\f' for c in text):
        raise ValueError('Binary-looking content')
    return text, requested

def make_pattern(find, case, words, regex):
    if not find:
        raise ValueError('Enter text to find.')
    expression = find if regex else re.escape(find)
    if words:
        expression = r'(?<!\w)(?:' + expression + r')(?!\w)'
    return re.compile(expression, 0 if case else re.IGNORECASE)

def transform(text, pattern, replacement, regex):
    return pattern.subn(replacement if regex else lambda m: replacement, text)

def safe_write(path, original, changed):
    if path.is_symlink() or path.read_bytes() != original:
        raise ValueError('File changed since preview; skipped')
    backup = path.with_name(path.name + '.bfr-backup-' +
                            datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    with backup.open('xb') as stream:
        stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
    shutil.copystat(path, backup)
    descriptor, name = tempfile.mkstemp(prefix='.bfr-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(changed)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(path, name)
        if path.is_symlink() or path.read_bytes() != original:
            raise ValueError('File changed during replacement; skipped')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return backup

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Batch Find and Replace — HTML and Text Files')
        self.geometry('1050x800')
        self.minsize(800,650)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.results = {}
        self.snapshot = None
        self.folder = tk.StringVar()
        self.filters = tk.StringVar(value='*.html;*.htm;*.css;*.js;*.txt;*.json;*.xml;*.md;*.py')
        self.excludes = tk.StringVar(value='.git;node_modules;__pycache__;venv;.venv')
        self.recursive = tk.BooleanVar(value=True)
        self.case = tk.BooleanVar(value=True)
        self.words = tk.BooleanVar()
        self.regex = tk.BooleanVar()
        self.encoding = tk.StringVar(value='Auto')
        self.limit = tk.StringVar(value='10')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TButton',padding=6)
        style.configure('Title.TLabel',font=('TkDefaultFont',17,'bold'),foreground='#184b70')
        body = ttk.Frame(self,padding=12)
        body.pack(fill='both',expand=True)
        body.columnconfigure(1,weight=1)
        ttk.Label(body,text='Batch Find and Replace',style='Title.TLabel').grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,12))
        ttk.Label(body,text='Folder').grid(row=1,column=0,sticky='w')
        ttk.Entry(body,textvariable=self.folder).grid(row=1,column=1,sticky='ew',padx=8)
        ttk.Button(body,text='Browse…',command=self.browse).grid(row=1,column=2)
        for row,label,var in [(2,'File patterns',self.filters),(3,'Exclude folders',self.excludes)]:
            ttk.Label(body,text=label).grid(row=row,column=0,sticky='w')
            ttk.Entry(body,textvariable=var).grid(row=row,column=1,columnspan=2,sticky='ew',padx=8,pady=3)
        options=ttk.Frame(body)
        options.grid(row=4,column=0,columnspan=3,sticky='ew',pady=6)
        for label,var in [('Include subfolders',self.recursive),('Match case',self.case),('Whole words',self.words),('Regular expression',self.regex)]:
            ttk.Checkbutton(options,text=label,variable=var).pack(side='left',padx=4)
        advanced=ttk.Frame(body)
        advanced.grid(row=5,column=0,columnspan=3,sticky='w',pady=4)
        ttk.Label(advanced,text='Encoding:').pack(side='left')
        ttk.Combobox(advanced,textvariable=self.encoding,values=['Auto','utf-8','utf-8-sig','cp1252','latin-1','utf-16','utf-16-le','utf-16-be'],state='readonly',width=12).pack(side='left',padx=8)
        ttk.Label(advanced,text='Maximum file size (MB):').pack(side='left')
        ttk.Entry(advanced,textvariable=self.limit,width=7).pack(side='left',padx=8)
        edit=ttk.Frame(body)
        edit.grid(row=6,column=0,columnspan=3,sticky='ew',pady=8)
        edit.columnconfigure(0,weight=1); edit.columnconfigure(1,weight=1)
        ttk.Label(edit,text='Find (multiline supported)').grid(row=0,column=0,sticky='w')
        ttk.Label(edit,text='Replace with (blank = delete)').grid(row=0,column=1,sticky='w')
        self.find=tk.Text(edit,height=4,wrap='none',undo=True,relief='sunken',borderwidth=2)
        self.replace=tk.Text(edit,height=4,wrap='none',undo=True,relief='sunken',borderwidth=2)
        self.find.grid(row=1,column=0,sticky='ew',padx=(0,6))
        self.replace.grid(row=1,column=1,sticky='ew',padx=(6,0))
        actions=ttk.Frame(body); actions.grid(row=7,column=0,columnspan=3,sticky='ew')
        self.buttons=[]
        for label,command in [('Preview',self.preview),('Replace selected',lambda:self.apply(True)),('Replace all results',lambda:self.apply(False)),('Save log',self.save_log),('Help',self.help)]:
            b=ttk.Button(actions,text=label,command=command); b.pack(side='left',padx=3);self.buttons.append(b)
        ttk.Button(actions,text='Cancel',command=self.cancel.set).pack(side='right')
        self.status=tk.StringVar(value='Choose a folder and enter your search, then click Preview. Backups are always created.')
        ttk.Label(body,textvariable=self.status,wraplength=980).grid(row=8,column=0,columnspan=3,sticky='ew',pady=8)
        self.progress=ttk.Progressbar(body,mode='indeterminate');self.progress.grid(row=9,column=0,columnspan=3,sticky='ew')
        pane=ttk.Panedwindow(body,orient='vertical');pane.grid(row=10,column=0,columnspan=3,sticky='nsew',pady=6);body.rowconfigure(10,weight=1)
        top=ttk.Frame(pane);pane.add(top,weight=1)
        self.tree=ttk.Treeview(top,columns=('file','count','encoding'),show='headings',selectmode='extended',height=7)
        for col,title,width in [('file','Matching file',650),('count','Matches',85),('encoding','Encoding',110)]:
            self.tree.heading(col,text=title);self.tree.column(col,width=width)
        scroll=ttk.Scrollbar(top,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self.show_diff)
        tabs=ttk.Notebook(pane);pane.add(tabs,weight=2)
        self.diff=self.text_tab(tabs,'Change preview')
        self.log=self.text_tab(tabs,'Run log')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self.poll)
    def text_tab(self,tabs,title):
        frame=ttk.Frame(tabs);tabs.add(frame,text=title)
        text=tk.Text(frame,wrap='none',state='disabled',font=('TkFixedFont',10))
        v=ttk.Scrollbar(frame,command=text.yview);h=ttk.Scrollbar(frame,orient='horizontal',command=text.xview)
        text.configure(yscrollcommand=v.set,xscrollcommand=h.set)
        frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        text.grid(row=0,column=0,sticky='nsew');v.grid(row=0,column=1,sticky='ns');h.grid(row=1,column=0,sticky='ew')
        return text
    def write(self,widget,text,clear=False):
        widget.configure(state='normal')
        if clear:widget.delete('1.0','end')
        widget.insert('end',text);widget.configure(state='disabled')
    def browse(self):
        value=filedialog.askdirectory()
        if value:self.folder.set(value)
    def settings(self):
        return (self.folder.get(),self.filters.get(),self.excludes.get(),self.recursive.get(),self.case.get(),self.words.get(),self.regex.get(),self.encoding.get(),self.limit.get(),self.find.get('1.0','end-1c'),self.replace.get('1.0','end-1c'))
    def start(self,job):
        self.busy=True;self.cancel.clear();self.progress.start()
        for b in self.buttons:b.configure(state='disabled')
        threading.Thread(target=job,daemon=True).start()
    def preview(self):
        if self.busy:return
        settings=self.settings()
        folder,filters,excluded,recursive,case,words,regex,encoding,limit,find,replacement=settings
        try:
            root=Path(folder).expanduser().resolve()
            if not folder or not root.is_dir():raise ValueError('Choose an existing folder.')
            patterns=[p.strip() for p in filters.split(';') if p.strip()]
            if not patterns:raise ValueError('Enter at least one file pattern.')
            maximum=float(limit)*1024*1024
            if not 0 < maximum < float('inf'):raise ValueError('Maximum size must be a positive number.')
            pattern=make_pattern(find,case,words,regex)
            if regex:pattern.sub(replacement,'')
        except (ValueError,re.error) as e:
            messagebox.showerror('Check search settings',str(e));return
        self.results.clear();self.tree.delete(*self.tree.get_children());self.write(self.diff,'',True)
        self.snapshot=settings
        def worker():
            scanned=skipped=matches=0
            excludes=[p.strip() for p in excluded.split(';') if p.strip()]
            try:
                def walk_error(e):self.events.put(('log',f'SCAN ERROR: {e}\n'))
                for directory,dirs,files in os.walk(root,followlinks=False,onerror=walk_error):
                    dirs[:]=[d for d in dirs if not Path(directory,d).is_symlink() and not any(fnmatch.fnmatchcase(d.lower(),p.lower()) for p in excludes)] if recursive else []
                    for name in files:
                        if self.cancel.is_set():break
                        path=Path(directory,name)
                        if path.is_symlink() or '.bfr-backup-' in name or name.startswith('.bfr-'):continue
                        if not any(fnmatch.fnmatchcase(name.lower(),p.lower()) for p in patterns):continue
                        scanned+=1
                        try:
                            if path.suffix.lower() in BINARY_EXT or path.stat().st_size>maximum:
                                skipped+=1;continue
                            with path.open('rb') as stream:raw=stream.read(int(maximum)+1)
                            if len(raw)>maximum:skipped+=1;continue
                            text,actual=decode_bytes(raw,encoding)
                            updated,count=transform(text,pattern,replacement,regex)
                            if count and updated!=text:
                                updated.encode(actual)
                                result=(path,hashlib.sha256(raw).hexdigest(),count,actual)
                                self.events.put(('result',result));matches+=count
                        except (OSError,UnicodeError,ValueError) as e:
                            skipped+=1;self.events.put(('log',f'SKIPPED {path}: {e}\n'))
                    if self.cancel.is_set():break
                self.events.put(('done',f'Preview {"canceled" if self.cancel.is_set() else "complete"}: {scanned} files checked; {matches} matches producing changes; {skipped} skipped.'))
            except Exception as e:self.events.put(('done',f'Preview error: {e}'))
        self.status.set('Scanning files…');self.start(worker)
    def show_diff(self,event=None):
        selected=self.tree.selection()
        if not selected or self.busy:return
        path,digest,count,encoding=self.results[selected[0]]
        try:
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('File has changed. Run Preview again.')
            text,_=decode_bytes(raw,encoding)
            s=self.snapshot;updated,_=transform(text,make_pattern(s[9],s[4],s[5],s[6]),s[10],s[6])
            diff=difflib.unified_diff(text.splitlines(True),updated.splitlines(True),fromfile=str(path),tofile='Proposed result')
            lines=[]
            for i,line in enumerate(diff):
                if i>=300:lines.append('\n[Preview truncated at 300 lines]\n');break
                lines.append(line[:4000]+('\n[Long line truncated]\n' if len(line)>4000 else ''))
            self.write(self.diff,''.join(lines),True)
        except Exception as e:self.write(self.diff,str(e),True)
    def apply(self,selected):
        if self.busy:return
        if self.settings()!=self.snapshot:
            messagebox.showinfo('Preview needed','Settings changed. Run Preview again before replacing.');return
        ids=self.tree.selection() if selected else self.tree.get_children()
        items=[self.results[i] for i in ids]
        if not items:messagebox.showinfo('No files','Preview first, then select matching files.');return
        if not messagebox.askyesno('Confirm replacements',f'Change {len(items)} files containing {sum(x[2] for x in items)} matches?\n\nA backup will be created beside each modified file.'):return
        s=self.snapshot
        def worker():
            done=failed=0
            try:
                pattern=make_pattern(s[9],s[4],s[5],s[6])
                for path,digest,count,encoding in items:
                    if self.cancel.is_set():break
                    try:
                        raw=path.read_bytes()
                        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Changed since preview')
                        text,_=decode_bytes(raw,encoding)
                        updated,_=transform(text,pattern,s[10],s[6])
                        backup=safe_write(path,raw,updated.encode(encoding));done+=1
                        self.events.put(('log',f'CHANGED {path}\n  Backup: {backup}\n'))
                    except Exception as e:
                        failed+=1;self.events.put(('log',f'FAILED {path}: {e}\n'))
                self.events.put(('applied',f'Replacement {"canceled" if self.cancel.is_set() else "complete"}: {done} files changed; {failed} failed. Run Preview for fresh results.'))
            except Exception as e:self.events.put(('applied',f'Replacement error: {e}'))
        self.status.set('Replacing files and creating backups…');self.start(worker)
    def poll(self):
        for _ in range(150):
            try:kind,value=self.events.get_nowait()
            except queue.Empty:break
            if kind=='result':
                key=str(len(self.results));self.results[key]=value
                self.tree.insert('', 'end',iid=key,values=(str(value[0]),value[2],value[3]))
            elif kind=='log':self.write(self.log,value)
            else:
                self.busy=False;self.progress.stop();self.status.set(value);self.write(self.log,value+'\n')
                for b in self.buttons:b.configure(state='normal')
                if kind=='applied':self.snapshot=None;self.results.clear();self.tree.delete(*self.tree.get_children())
        self.after(100,self.poll)
    def save_log(self):
        path=filedialog.asksaveasfilename(defaultextension='.txt',initialfile='find_replace_log.txt')
        if path:
            try:Path(path).write_text(self.log.get('1.0','end-1c'),encoding='utf-8')
            except OSError as e:messagebox.showerror('Cannot save log',str(e))
    def help(self):
        window=tk.Toplevel(self);window.title('Instructions');window.geometry('780x650')
        text=tk.Text(window,wrap='word',padx=15,pady=15)
        scroll=ttk.Scrollbar(window,command=text.yview);text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('1.0',HELP);text.configure(state='disabled')
    def close(self):
        if self.busy:
            self.cancel.set();messagebox.showinfo('Stopping','Cancel requested. Wait for the current file to finish, then close again.');return
        self.destroy()

if __name__=='__main__':
    App().mainloop()
