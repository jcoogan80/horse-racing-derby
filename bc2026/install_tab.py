"""Inject the KEE BC tab into web/index.html (idempotent: replaces the marked blocks if present)."""
import re, os
here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, '..', 'web', 'index.html')
s = open(path, encoding='utf-8').read()
css = open(os.path.join(here, 'kee_bc_tab.css')).read()
pane = open(os.path.join(here, 'kee_bc_tab.html')).read()
js = open(os.path.join(here, 'kee_bc_tab.js')).read()

def put(s, tag, content, anchor, before=True):
    a, b = f'/*<{tag}>*/' if tag.endswith('css') else f'<!--<{tag}>-->', f'/*</{tag}>*/' if tag.endswith('css') else f'<!--</{tag}>-->'
    block = f'{a}\n{content}\n{b}'
    if a in s:
        return re.sub(re.escape(a) + r'.*?' + re.escape(b), lambda m: block, s, flags=re.S)
    i = s.rindex(anchor) if anchor == '\n</html>' else s.index(anchor)
    return s[:i] + block + '\n' + s[i:] if before else s[:i + len(anchor)] + '\n' + block + s[i + len(anchor):]

s = put(s, 'kbc-css', css, '  </style>')
s = put(s, 'kbc-btn', """  <button class="tab-btn"         onclick="showTab('keebc')">KEE BC</button>""", '</nav>')
s = put(s, 'kbc-pane', pane, '<div id="tab-optixeq" class="tab-pane">')
s = put(s, 'kbc-js', '<script>\n' + js + '\n</script>', '\n</html>')
old = "const names = ['dashboard', 'hedge', 'trackguide', 'ticket', 'parlay', 'today', 'howto', 'optixeq', 'raceday', 'ticketgen'];"
if old in s:
    s = s.replace(old, "const names = ['dashboard', 'hedge', 'trackguide', 'ticket', 'parlay', 'today', 'howto', 'optixeq', 'raceday', 'ticketgen', 'keebc'];\n  if (name === 'keebc' && typeof kbcInit === 'function') kbcInit();")
open(path, 'w', encoding='utf-8').write(s)
print('installed', len(s))
