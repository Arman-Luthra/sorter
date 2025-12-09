import os
import shutil
import subprocess
import base64
import fitz
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor
import asyncio

app = FastAPI()
preview_cache = {}
executor = ThreadPoolExecutor(max_workers=8)

def render_pdf_preview(pdf_path: str, target_width: int = 1200) -> str:
    if pdf_path in preview_cache:
        return preview_cache[pdf_path]
    
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        page_width = page.rect.width
        scale = target_width / page_width
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csGRAY)
        img_bytes = pix.tobytes("jpeg", 75)
        doc.close()
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        preview_cache[pdf_path] = b64
        return b64
    except:
        return None

def render_all_pages(pdf_path: str, target_width: int = 1200) -> list:
    cache_key = pdf_path + "_all"
    if cache_key in preview_cache:
        return preview_cache[cache_key]
    
    try:
        doc = fitz.open(pdf_path)
        pages = []
        for page in doc:
            page_width = page.rect.width
            scale = target_width / page_width
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csGRAY)
            img_bytes = pix.tobytes("jpeg", 70)
            b64 = base64.b64encode(img_bytes).decode('utf-8')
            pages.append(b64)
        doc.close()
        preview_cache[cache_key] = pages
        return pages
    except:
        return []

def open_folder_dialog():
    import platform
    import sys
    
    system = platform.system()
    
    if system == "Darwin":
        script = '''
        tell application "System Events"
            activate
            set theFolder to choose folder with prompt "Select a folder"
            return POSIX path of theFolder
        end tell
        '''
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except:
            pass
    
    elif system == "Windows":
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory()
            root.destroy()
            if folder:
                return folder
        except:
            pass
    
    else:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            folder = filedialog.askdirectory()
            root.destroy()
            if folder:
                return folder
        except:
            pass
    
    return None

@app.get("/api/pick-folder")
async def pick_folder():
    folder = open_folder_dialog()
    if folder:
        return {"path": folder}
    return {"path": None}

class DirectoryRequest(BaseModel):
    path: str

class MoveRequest(BaseModel):
    source: str
    destination_folder: str
    pages_to_keep: int = 0
    backup_folder: str = ""

class PreviewRequest(BaseModel):
    path: str

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.post("/api/scan-directory")
async def scan_directory(request: DirectoryRequest):
    path = Path(request.path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    
    pdfs = []
    for file in path.iterdir():
        if file.suffix.lower() == ".pdf":
            pdfs.append({
                "name": file.name,
                "path": str(file.absolute())
            })
    
    pdfs = sorted(pdfs, key=lambda x: x["name"])
    
    loop = asyncio.get_event_loop()
    for pdf in pdfs[:10]:
        loop.run_in_executor(executor, render_pdf_preview, pdf["path"])
    
    return {"pdfs": pdfs}

@app.post("/api/preview")
async def get_preview(request: PreviewRequest):
    path = request.path
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    
    loop = asyncio.get_event_loop()
    preview = await loop.run_in_executor(executor, render_pdf_preview, path)
    
    if preview:
        return {"preview": preview}
    raise HTTPException(status_code=500, detail="Failed to render preview")

@app.post("/api/all-pages")
async def get_all_pages(request: PreviewRequest):
    path = request.path
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    
    loop = asyncio.get_event_loop()
    pages = await loop.run_in_executor(executor, render_all_pages, path)
    
    return {"pages": pages}

@app.post("/api/page-count")
async def get_page_count(request: PreviewRequest):
    path = request.path
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    
    try:
        doc = fitz.open(path)
        count = len(doc)
        doc.close()
        return {"count": count}
    except:
        raise HTTPException(status_code=500, detail="Failed to read PDF")

class UndoRequest(BaseModel):
    sorted_path: str
    backup_path: str
    original_folder: str

@app.post("/api/undo-move")
async def undo_move(request: UndoRequest):
    sorted_path = Path(request.sorted_path)
    backup_path = Path(request.backup_path) if request.backup_path else None
    original_folder = Path(request.original_folder)
    
    try:
        if sorted_path.exists():
            sorted_path.unlink()
        
        if backup_path and backup_path.exists():
            original_name = backup_path.name
            original_dest = original_folder / original_name
            shutil.move(str(backup_path), str(original_dest))
            return {"success": True, "restored_path": str(original_dest)}
        
        return {"success": True, "restored_path": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to undo: {str(e)}")

@app.get("/api/preview-image/{pdf_path:path}")
async def get_preview_image(pdf_path: str):
    if not pdf_path.startswith("/"):
        pdf_path = "/" + pdf_path
    
    if not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    
    loop = asyncio.get_event_loop()
    
    if pdf_path in preview_cache:
        img_bytes = base64.b64decode(preview_cache[pdf_path])
    else:
        try:
            doc = fitz.open(pdf_path)
            page = doc[0]
            target_width = 1400
            scale = target_width / page.rect.width
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("jpeg", 90)
            doc.close()
            preview_cache[pdf_path] = base64.b64encode(img_bytes).decode('utf-8')
        except:
            raise HTTPException(status_code=500, detail="Failed to render")
    
    return Response(content=img_bytes, media_type="image/jpeg", headers={
        "Cache-Control": "public, max-age=86400"
    })

@app.post("/api/validate-folder")
async def validate_folder(request: DirectoryRequest):
    path = Path(request.path).expanduser()
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cannot create folder: {str(e)}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    return {"valid": True, "path": str(path.absolute())}

@app.post("/api/move-pdf")
async def move_pdf(request: MoveRequest):
    source = Path(request.source)
    dest_folder = Path(request.destination_folder)
    pages_to_keep = request.pages_to_keep
    backup_folder = Path(request.backup_folder) if request.backup_folder else None
    
    if not source.exists():
        raise HTTPException(status_code=404, detail="Source file not found")
    if not dest_folder.exists():
        raise HTTPException(status_code=404, detail="Destination folder not found")
    
    destination = dest_folder / source.name
    
    if destination.exists():
        base = source.stem
        suffix = source.suffix
        counter = 1
        while destination.exists():
            destination = dest_folder / f"{base}_{counter}{suffix}"
            counter += 1
    
    old_path = str(source)
    if old_path in preview_cache:
        del preview_cache[old_path]
    cache_key = old_path + "_all"
    if cache_key in preview_cache:
        del preview_cache[cache_key]
    
    backup_path = None
    
    try:
        if pages_to_keep > 0 and backup_folder:
            backup_folder.mkdir(parents=True, exist_ok=True)
            backup_dest = backup_folder / source.name
            if backup_dest.exists():
                base = source.stem
                suffix = source.suffix
                counter = 1
                while backup_dest.exists():
                    backup_dest = backup_folder / f"{base}_{counter}{suffix}"
                    counter += 1
            
            shutil.copy2(str(source), str(backup_dest))
            backup_path = str(backup_dest)
            
            doc = fitz.open(str(source))
            total_pages = len(doc)
            pages_to_extract = min(pages_to_keep, total_pages)
            
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=0, to_page=pages_to_extract - 1)
            new_doc.save(str(destination))
            new_doc.close()
            doc.close()
            
            source.unlink()
        else:
            shutil.move(str(source), str(destination))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to move file: {str(e)}")
    
    return {"success": True, "new_path": str(destination), "backup_path": backup_path}

@app.get("/api/pdf/{pdf_path:path}")
async def get_pdf(pdf_path: str):
    if not pdf_path.startswith("/"):
        pdf_path = "/" + pdf_path
    path = Path(pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        path, 
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Accept-Ranges": "bytes"
        }
    )

app.mount("/static", StaticFiles(directory="static"), name="static")
