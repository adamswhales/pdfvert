import os, io, tempfile
from flask import Flask, render_template, request, send_file, redirect, url_for, abort, make_response
from werkzeug.utils import secure_filename
import config
from PyPDF2 import PdfMerger
from PIL import Image
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from moviepy.editor import VideoFileClip
import pikepdf
from rembg import remove

app = Flask(__name__)
app.config.from_object(config)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_FILE_SIZE_MB * 1024 * 1024

TOOLS = {
    "compress-pdf": {"title":"Compress PDF","accept":".pdf","multiple":False, "desc": "Reduce PDF size by optimizing content and structure. Perfect for email or uploads."},
    "merge-pdf": {"title":"Merge PDF","accept":".pdf","multiple":True, "desc": "Combine multiple PDF files into one in the order you upload them."},
    "word-to-pdf": {"title":"Word → PDF","accept":".docx","multiple":False, "desc": "Convert DOCX into a simple, shareable PDF."},
    "png-to-pdf": {"title":"PNG → PDF","accept":".png","multiple":True, "desc": "Convert one or multiple PNG images into a single PDF document."},
    "png-to-jpg": {"title":"PNG → JPG","accept":".png","multiple":False, "desc": "Convert transparent PNG into JPG for smaller file size."},
    "jpg-to-png": {"title":"JPG → PNG","accept":".jpg,.jpeg","multiple":False, "desc": "Convert JPG to PNG (supports transparency)."},
    "image-compressor": {"title":"Image Compressor","accept":".jpg,.jpeg,.png","multiple":False, "desc": "Compress images to reduce size with minimal quality loss."},
    "remove-bg": {"title":"Background Remover","accept":".jpg,.jpeg,.png","multiple":False, "desc": "Remove background from photos using AI."},
    "mp4-to-mp3": {"title":"MP4 → MP3","accept":".mp4","multiple":False, "desc": "Extract audio from video into MP3 format."},
    "video-compressor": {"title":"Video Compressor","accept":"video/*","multiple":False, "desc": "Compress video to a shareable size with good quality."},
    "video-to-gif": {"title":"Video → GIF","accept":"video/*","multiple":False, "desc": "Create a short animated GIF from your video."},
}

@app.context_processor
def inject_globals():
    return dict(config=config, SITE_NAME=config.SITE_NAME)

@app.route('/favicon.ico')
def favicon():
    return send_file(os.path.join('static','favicon.ico'))

@app.route('/robots.txt')
def robots():
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {config.SITE_URL.rstrip('/')}/sitemap.xml"
    ]
    resp = make_response("\n".join(lines), 200)
    resp.headers["Content-Type"] = "text/plain"
    return resp

@app.route('/sitemap.xml')
def sitemap():
    base = config.SITE_URL.rstrip('/')
    urls = ["/", "/how-to-use"] + [f"/tool/{slug}" for slug in TOOLS.keys()]
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml_parts.append(f"<url><loc>{base}{u}</loc></url>")
    xml_parts.append("</urlset>")
    resp = make_response("\n".join(xml_parts), 200)
    resp.headers["Content-Type"] = "application/xml"
    return resp

@app.route('/')
def index():
    title = f"{config.SITE_NAME} – Free Online File Converter Tools"
    description = "Convert PDF, PNG, JPG, and MP4 with PDFvert — free, fast, and no login required. Compress PDFs, merge files, convert images and videos online."
    return render_template('index.html', tools=TOOLS, title=title, description=description)

@app.route('/how-to-use')
def how_to_use():
    title = f"How to Use {config.SITE_NAME} – Quick Guide"
    description = "Learn how to convert and compress files with PDFvert. Free online tools for PDF, image, and video with no sign-up."
    return render_template('how-to-use.html', title=title, description=description)

def send_bytesio(bytes_data, mimetype, filename):
    bio = io.BytesIO(bytes_data)
    bio.seek(0)
    return send_file(bio, as_attachment=True, download_name=filename, mimetype=mimetype)

def cleanup(paths):
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except: pass

@app.route('/tool/<slug>', methods=['GET','POST'])
def tool(slug):
    if slug not in TOOLS:
        abort(404)
    cfg = TOOLS[slug]
    page_title = f"{cfg['title']} Online – Free & Fast | {config.SITE_NAME}"
    page_desc = f"Use {config.SITE_NAME} to {cfg['title']} online. Free, secure, and no sign‑up. Upload your file and download instantly."

    if request.method == 'GET':
        return render_template('tool.html', tool_slug=slug, tool_name=cfg['title'], accept=cfg['accept'], multiple=cfg['multiple'], desc=cfg['desc'], title=page_title, description=page_desc)

    # POST: handle uploads and process
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return redirect(request.url)
    saved = []
    try:
        for f in files:
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)
            saved.append(path)

        # Dispatch per slug
        if slug == 'compress-pdf':
            src = saved[0]
            with pikepdf.open(src) as pdf:
                pdf.remove_unreferenced_resources()
                out = io.BytesIO()
                pdf.save(out, linearize=True)
                return send_bytesio(out.getvalue(), 'application/pdf', 'compressed.pdf')

        if slug == 'merge-pdf':
            merger = PdfMerger()
            for p in saved:
                merger.append(p)
            out = io.BytesIO()
            merger.write(out); merger.close()
            return send_bytesio(out.getvalue(), 'application/pdf', 'merged.pdf')

        if slug == 'word-to-pdf':
            doc = Document(saved[0])
            out = io.BytesIO()
            c = canvas.Canvas(out, pagesize=A4)
            width, height = A4
            x, y = 40, height - 40
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    y -= 14
                    if y < 60:
                        c.showPage(); y = height - 40
                    continue
                for line in text.split('\n'):
                    c.drawString(x, y, line[:110])
                    y -= 14
                    if y < 60:
                        c.showPage(); y = height - 40
            c.save()
            return send_bytesio(out.getvalue(), 'application/pdf', 'document.pdf')

        if slug == 'png-to-pdf':
            imgs = [Image.open(p).convert('RGB') for p in saved]
            out = io.BytesIO()
            if len(imgs) == 1:
                imgs[0].save(out, format='PDF')
            else:
                imgs[0].save(out, format='PDF', save_all=True, append_images=imgs[1:])
            return send_bytesio(out.getvalue(), 'application/pdf', 'images.pdf')

        if slug == 'png-to-jpg':
            img = Image.open(saved[0]).convert('RGB')
            out = io.BytesIO(); img.save(out, format='JPEG', quality=85, optimize=True)
            return send_bytesio(out.getvalue(), 'image/jpeg', 'image.jpg')

        if slug == 'jpg-to-png':
            img = Image.open(saved[0]).convert('RGBA')
            out = io.BytesIO(); img.save(out, format='PNG', optimize=True)
            return send_bytesio(out.getvalue(), 'image/png', 'image.png')

        if slug == 'image-compressor':
            img = Image.open(saved[0])
            if img.mode != 'RGB': img = img.convert('RGB')
            out = io.BytesIO(); img.save(out, format='JPEG', quality=60, optimize=True)
            return send_bytesio(out.getvalue(), 'image/jpeg', 'compressed.jpg')

        if slug == 'remove-bg':
            with open(saved[0],'rb') as f: data = f.read()
            out = remove(data)
            return send_bytesio(out, 'image/png', 'no-bg.png')

        if slug == 'mp4-to-mp3':
            src = saved[0]
            clip = VideoFileClip(src)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            clip.audio.write_audiofile(tmp.name, fps=44100, bitrate='192k')
            clip.close()
            with open(tmp.name,'rb') as f:
                d = f.read()
            os.remove(tmp.name)
            return send_bytesio(d, 'audio/mpeg', 'audio.mp3')

        if slug == 'video-compressor':
            src = saved[0]
            clip = VideoFileClip(src)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            clip.write_videofile(tmp.name, codec='libx264', audio_codec='aac', bitrate='900k', preset='medium')
            clip.close()
            with open(tmp.name,'rb') as f: d = f.read()
            os.remove(tmp.name)
            return send_bytesio(d, 'video/mp4', 'compressed.mp4')

        if slug == 'video-to-gif':
            src = saved[0]
            clip = VideoFileClip(src)
            duration = min(10, clip.duration or 10)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.gif')
            clip.subclip(0, duration).write_gif(tmp.name, fps=10)
            clip.close()
            with open(tmp.name,'rb') as f: d = f.read()
            os.remove(tmp.name)
            return send_bytesio(d, 'image/gif', 'clip.gif')

    finally:
        # cleanup uploads
        for p in saved:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except: pass

    abort(400)

@app.errorhandler(413)
def too_large(e):
    return f"File too large. Max is {app.config['MAX_CONTENT_LENGTH']//1024//1024} MB", 413

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
