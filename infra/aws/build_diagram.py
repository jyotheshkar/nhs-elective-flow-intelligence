from pathlib import Path
import html
import xml.etree.ElementTree as ET

OUT=Path('docs/aws')
nodes=[
 ('source',60,140,300,105,'NHS England RTT publications','Monthly public aggregate workbooks','external'),
 ('schedule',460,140,300,105,'Amazon EventBridge Scheduler','Weekly discovery; Europe/London','control'),
 ('ecr',860,140,300,105,'Amazon ECR','Immutable-tagged workload image','control'),
 ('batch',460,340,300,120,'Amazon ECS on AWS Fargate','Python ingestion + analytics build','compute'),
 ('s3',60,560,300,120,'Amazon S3','Private versioned raw + releases','storage'),
 ('gate',460,560,300,120,'Operator release review','Pin approved ReleaseId via CloudFormation','gate'),
 ('api',860,560,300,120,'AWS App Runner','FastAPI + local read-only DuckDB','compute'),
 ('ui',860,800,300,105,'Vercel / Next.js','Existing dashboard; external hosting','external'),
 ('monitor',60,800,700,105,'CloudWatch + EventBridge + Amazon SNS','Build logs, refresh failures, task-stop notifications','control'),
]
edges=[('source','batch','HTTPS download'),('schedule','batch','ECS RunTask'),('ecr','batch','Pull image'),('batch','s3','Validated artifacts + hashes'),('s3','gate','Manifest / evidence review'),('gate','api','Deploy approved ID'),('s3','api','Download pinned snapshot'),('api','ui','HTTPS JSON'),('batch','monitor','Logs + task state')]
colors={'external':('#162331','#668195'),'control':('#102d3b','#35c5df'),'compute':('#34251b','#f0a34b'),'storage':('#17342b','#62c59b'),'gate':('#322a43','#b19bdc')}
parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="1040" viewBox="0 0 1280 1040">', '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#a7b9c9"/></marker></defs>', '<rect width="1280" height="1040" fill="#0a1420"/>','<text x="60" y="54" fill="#f4f7fb" font-family="Arial" font-size="30" font-weight="bold">NHS Elective Flow Intelligence</text>','<text x="60" y="88" fill="#a7b9c9" font-family="Arial" font-size="17">AWS deployment design | public statistics only | London eu-west-2 | prepared, not deployed</text>']
# Routing paths are explicit so labels do not run across component boxes.
paths=[
 ('M 360 192 L 410 192 L 410 400 L 460 400',370,300,'HTTPS download'),
 ('M 610 245 L 610 340',625,290,'RunTask'),
 ('M 1010 245 L 1010 395 L 760 395',810,380,'Pull image'),
 ('M 460 430 L 210 430 L 210 560',220,485,'Validated files + hashes'),
 ('M 360 620 L 460 620',365,605,'Review'),
 ('M 760 620 L 860 620',765,605,'Pin ID'),
 ('M 210 680 L 210 735 L 1010 735 L 1010 680',475,720,'S3 GetObject: exact approved release prefix'),
 ('M 1010 800 L 1010 755',1025,785,'HTTPS API calls'),
 ('M 610 460 L 810 460 L 810 775 L 610 775 L 610 800',620,760,'Logs / task stop'),
]
for path,x,y,label in paths:
 parts.append(f'<path d="{path}" fill="none" stroke="#a7b9c9" stroke-width="2" marker-end="url(#arrow)"/>')
 parts.append(f'<text x="{x}" y="{y}" fill="#c4d2dd" font-family="Arial" font-size="13">{html.escape(label)}</text>')
for ident,x,y,w,h,title,sub,kind in nodes:
 fill,stroke=colors[kind]
 parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
 parts.append(f'<text x="{x+18}" y="{y+36}" fill="#f4f7fb" font-family="Arial" font-size="18" font-weight="bold">{html.escape(title)}</text>')
 # text width target <= roughly 42 chars per line
 import textwrap
 for i,line in enumerate(textwrap.wrap(sub,42 if w<400 else 90)):
  parts.append(f'<text x="{x+18}" y="{y+64+i*20}" fill="#c4d2dd" font-family="Arial" font-size="14">{html.escape(line)}</text>')
parts+=['<text x="60" y="958" fill="#dce8f1" font-family="Arial" font-size="16">Failure protection: candidates do not change the serving release. Verify checksums before API startup.</text>','<text x="60" y="988" fill="#8ea5b8" font-family="Arial" font-size="14">IAM least privilege | encryption | source provenance | precomputed analytics | documented rollback | bounded compute</text>','</svg>']
(OUT/'Architecture.svg').write_text('\n'.join(parts),encoding='utf-8')
mx=ET.Element('mxfile',host='app.diagrams.net');diag=ET.SubElement(mx,'diagram',name='AWS Public Statistics Architecture',id='nhs-aws');model=ET.SubElement(diag,'mxGraphModel',dx='1280',dy='1040',grid='1',page='1',pageWidth='1280',pageHeight='1040');root=ET.SubElement(model,'root');ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
for ident,x,y,w,h,title,sub,kind in nodes:
 fill,stroke=colors[kind]
 cell=ET.SubElement(root,'mxCell',id=ident,value=title+'\n'+sub,style=f'rounded=1;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={stroke};fontColor=#f4f7fb;fontSize=16;',vertex='1',parent='1')
 ET.SubElement(cell,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
for i,(source,target,label) in enumerate(edges):
 cell=ET.SubElement(root,'mxCell',id='edge'+str(i),value=label,style='edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;fontSize=13;',edge='1',parent='1',source=source,target=target)
 ET.SubElement(cell,'mxGeometry',relative='1',attrib={'as':'geometry'})
ET.indent(mx)
(OUT/'Architecture.drawio').write_bytes(ET.tostring(mx,encoding='utf-8',xml_declaration=True))
ET.parse(OUT/'Architecture.svg'); ET.parse(OUT/'Architecture.drawio')
print('SVG and editable drawio XML valid')
