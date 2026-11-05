"""Render the maintained design to HTML/PDF with the bundled document runtime."""
from pathlib import Path
import html,json,re,subprocess,sys,hashlib


def blocks(text):
    lines=text.splitlines();i=0
    while i<len(lines):
        s=lines[i]
        if not s.strip():i+=1;continue
        if s.startswith('```'):
            code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
            yield 'code','\n'.join(code);i+=1;continue
        if s.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                cells=[x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r'[-: ]+',x) for x in cells):rows.append(cells)
                i+=1
            yield 'table',rows;continue
        if s.startswith('#'):
            level=len(s)-len(s.lstrip('#'));yield 'h'+str(level),s[level:].strip();i+=1;continue
        p=[s];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','```','- ')) and not re.match(r'\d+\. ',lines[i]):p.append(lines[i]);i+=1
        yield 'p',' '.join(p)


def inline(s):
    s=html.escape(s)
    s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font face="Courier">\1</font>',s)
    return re.sub(r'\[([^]]+)\]\((https?://[^)]+)\)',r'<a href="\2">\1</a>',s)


def pdf_worker(folder):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Preformatted,Image
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_LEFT
    pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Bold','C:/Windows/Fonts/arialbd.ttf'))
    pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial',boldItalic='Arial-Bold')
    styles=getSampleStyleSheet()
    for name in ['Normal','BodyText','Heading1','Heading2','Title']:
        styles[name].fontName='Arial';styles[name].textColor=colors.HexColor('#183047')
    styles['BodyText'].fontSize=9;styles['BodyText'].leading=13;styles['BodyText'].spaceAfter=8
    styles['Title'].fontSize=22;styles['Title'].leading=27;styles['Title'].keepWithNext=True
    styles['Heading2'].keepWithNext=True
    styles['Heading2'].fontSize=14;styles['Heading2'].leading=18;styles['Heading2'].spaceBefore=14
    cell=ParagraphStyle('cell',parent=styles['BodyText'],fontSize=7.5,leading=10,spaceAfter=0)
    story=[]
    for kind,data in blocks((folder/'DESIGN_REPORT.md').read_text(encoding='utf-8')):
        if kind=='table':
            rows=[[Paragraph(inline(v),cell) for v in row] for row in data]
            n=len(rows[0]);widths=([155,340] if n==2 else [95,240,160] if n==3 else [80,180,160,75] if n==4 else [495/n]*n)
            table=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dfeaf3')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOX',(0,0),(-1,-1),.3,colors.HexColor('#9eafbc')),('INNERGRID',(0,0),(-1,-1),.2,colors.HexColor('#c5d2dc')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            story.extend([table,Spacer(1,10)])
        elif kind=='h1':
            story.extend([Paragraph(inline(data),styles['Title']),Spacer(1,12),Spacer(1,12)])
        elif kind=='code':
            # Break commands only for presentation; Markdown retains exact runnable text.
            import textwrap
            story.append(Preformatted('\n'.join(textwrap.fill(x,90,subsequent_indent='  ') for x in data.splitlines()),ParagraphStyle('code',fontName='Courier',fontSize=7,leading=10)))
        else:story.append(Paragraph(inline(data),styles['Title' if kind=='h1' else 'Heading2' if kind.startswith('h') else 'BodyText']))
    def footer(canvas,doc):
        canvas.setFont('Arial',8);canvas.setFillColor(colors.HexColor('#61778a'));canvas.drawString(50,28,'QC Research | Design 0.8.7 | 27 October 2026');canvas.drawRightString(545,28,str(doc.page))
    SimpleDocTemplate(str(folder/'DESIGN_REPORT.pdf'),pagesize=(595,842),rightMargin=50,leftMargin=50,topMargin=42,bottomMargin=45,title='Design 0.8.7 0DTE strategy PoC design',author='QC Research').build(story,onFirstPage=footer,onLaterPages=footer)


def main():
    folder=Path(__file__).resolve().parent
    text=(folder/'DESIGN_REPORT.md').read_text();parts=[]
    for kind,data in blocks(text):
        if kind=='table':
            rows=[]
            for idx,row in enumerate(data):
                tag='th' if idx==0 else 'td';rows.append('<tr>'+''.join(f'<{tag}>{inline(x)}</{tag}>' for x in row)+'</tr>')
            parts.append('<table>'+''.join(rows)+'</table>')
        elif kind=='code':parts.append('<pre>'+html.escape(data)+'</pre>')
        else:parts.append(f'<{kind}>{inline(data)}</{kind}>')
    style='body{font:16px/1.6 system-ui;color:#183047;max-width:1120px;margin:40px auto;padding:0 28px}h1{font-size:34px}h2{margin-top:36px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #c5d2dc;text-align:left;vertical-align:top;padding:10px}th{background:#dfeaf3}pre{background:#eef3f7;padding:16px;white-space:pre-wrap}'
    (folder/'DESIGN_REPORT.html').write_text('<!doctype html><html><head><meta charset="utf-8"><title>Design 0.8.7 0DTE strategy PoC design</title><style>'+style+'</style></head><body>'+''.join(parts)+''+'</body></html>')
    (folder/'DESIGN_REPORT.txt').write_text(text)
    runtime='/mnt/c/Users/victo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    win_path=subprocess.check_output(['wslpath','-w',str(Path(__file__).resolve())],text=True).strip()
    win_folder=subprocess.check_output(['wslpath','-w',str(folder)],text=True).strip()
    subprocess.run([runtime,win_path,'--pdf-worker',win_folder],check=True)
    files=['DESIGN_REPORT.md','DESIGN_REPORT.txt','DESIGN_REPORT.html','DESIGN_REPORT.pdf','experiment_contract.json','coverage_snapshot.json','audit_coverage.py','build_report.py']
    (folder/'manifest.json').write_text(json.dumps({'version':'0.8.7','files':{n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in files}},indent=2)+'\n')
    print('Rendered',folder/'DESIGN_REPORT.pdf')

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--pdf-worker':pdf_worker(Path(sys.argv[2]))
    else:main()
