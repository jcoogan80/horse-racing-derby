import subprocess, sys
from PIL import Image, ImageDraw, ImageFont
DPI=200; S=DPI/72
jobs={('fri',1):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',1),('fri',2):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',3),('fri',3):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',5),('fri',4):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',7),('fri',5):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',9),('sat',1):('a5e135d9-OptixPlot___KEE_R12_2026-10-31.PDF',1),('sat',2):('a5e135d9-OptixPlot___KEE_R12_2026-10-31.PDF',3),('sat',3):('a5e135d9-OptixPlot___KEE_R12_2026-10-31.PDF',5),('fri',6):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',11),('fri',7):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',13),('fri',8):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',15),('fri',9):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',17),('fri',10):('657beffe-OptixPlot___KEE_R10_2026-10-30.PDF',19)}
for r,p in zip(range(4,13),range(7,24,2)): jobs[('sat',r)]=('a5e135d9-OptixPlot___KEE_R12_2026-10-31.PDF',p)
for (d,r),(f,p) in jobs.items():
    subprocess.run(['pdftoppm','-r',str(DPI),'-png','-f',str(p),'-l',str(p),'-singlefile',f,f'imgs/{d}{r}'],check=True)
    im=Image.open(f'imgs/{d}{r}.png').convert('RGB')
    out=[]
    # frames (pt): standard x 62.6..302.4, y 186.5..427.7 ; surfdist offset by +274.4 in x
    for ox in (0,274.4):
        x0,x1,y0,y1=(62.6+ox)*S,(302.4+ox)*S,186.5*S,427.7*S
        crop=im.crop((int(x0-40),int(y0-20),int(x1+20),int(y1+30)))
        dr=ImageDraw.Draw(crop)
        for k in range(-6,7):
            v=k/2
            gx=(x0-(x0-40))+(v+3)/6*(x1-x0); gy=(y0-(y0-20))+(3-v)/6*(y1-y0)
            col=(255,0,0) if k%2==0 else (255,170,170)
            dr.line([(gx,20),(gx,20+(y1-y0))],fill=col,width=1)
            dr.line([(40,gy),(40+(x1-x0),gy)],fill=col,width=1)
            dr.text((gx-6,(y1-y0)+22),f'{v:g}',fill=(200,0,0))
            dr.text((2,gy-5),f'{v:g}',fill=(200,0,0))
        out.append(crop)
    w=sum(c.width for c in out)+10; h=max(c.height for c in out)
    comp=Image.new('RGB',(w,h),'white'); comp.paste(out[0],(0,0)); comp.paste(out[1],(out[0].width+10,0))
    comp.save(f'imgs/grid_{d}{r}.png')
print('ok')
