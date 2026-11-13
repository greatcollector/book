#!/usr/bin/env python3
"""Rebuildable, offline TF-IDF vector search. No external APIs or model weights."""
import argparse, collections, hashlib, json, math, re, sqlite3, zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

class TolerantBlocks(HTMLParser):
    """Fallback for malformed publisher HTML; collects only visible body blocks."""
    def __init__(self):
        super().__init__(convert_charrefs=True); self.body=False; self.skip=0; self.depth=0; self.buf=[]; self.blocks=[]
    def handle_starttag(self,tag,attrs):
        if tag=="body": self.body=True
        if tag in ("script","style","nav"): self.skip+=1
        if self.body and not self.skip and tag in ("p","h1","h2","h3","h4","h5","h6","li","pre"):
            self.depth+=1
    def handle_endtag(self,tag):
        if tag in ("script","style","nav"): self.skip=max(0,self.skip-1)
        if tag in ("p","h1","h2","h3","h4","h5","h6","li","pre") and self.depth:
            self.depth-=1
            if not self.depth:
                text=" ".join("".join(self.buf).split()); self.buf=[]
                if text:self.blocks.append(text)
        if tag=="body":self.body=False
    def handle_data(self,data):
        if self.body and self.depth and not self.skip:self.buf.append(data)

STOP = set('a an the and or of to in on for is are was were be been being that this with as it its at by from not but you your i we our they their he his she her'.split())

def terms(text):
    """English words + Chinese bigrams/trigrams. No single-character matches."""
    out=[t for t in re.findall(r"[a-z]+(?:'[a-z]+)?",text.lower()) if t not in STOP]
    for run in re.findall(r"[\u3400-\u9fff]+",text):
        for n in (2,3):out.extend(run[i:i+n] for i in range(len(run)-n+1))
    return out

def eligible_blocks(blocks,exclude_documents=()):
    """Keep extraction intact; remove TOCs and short Chinese fragments from search."""
    blocks=list(blocks);groups=collections.defaultdict(list)
    for loc,t in blocks:groups[loc.split('#')[0]].append(t)
    excluded=set(exclude_documents)
    for doc,ts in groups.items():
        headings=sum(bool(re.match(r'^第[一二三四五六七八九十百0-9]+章',t)) for t in ts)
        if headings>=5 and headings/len(ts)>=0.4:excluded.add(doc)
    for loc,t in blocks:
        if loc.split('#')[0] in excluded:continue
        if len(re.findall(r'[\u3400-\u9fff]',t))>=1 and len(t)<45:continue
        yield loc,t

def extract(path):
    """Yield source locators and text, in EPUB spine or TXT paragraph order."""
    path=Path(path)
    if path.suffix.lower()=='.txt':
        for i,p in enumerate(re.split(r'\n\s*\n',path.read_text(encoding='utf-8-sig')),1):
            if p.strip(): yield f'paragraph:{i}', ' '.join(p.split())
    elif path.suffix.lower()=='.epub':
        with zipfile.ZipFile(path) as z:
            container=ET.fromstring(z.read('META-INF/container.xml'))
            opf=next(x.attrib['full-path'] for x in container.iter() if x.tag.endswith('rootfile'))
            root=ET.fromstring(z.read(opf)); base=Path(opf).parent
            items={x.attrib['id']:x.attrib['href'] for x in root.iter() if x.tag.split('}')[-1]=='item'}
            for spine in root.iter():
                if spine.tag.split('}')[-1]!='itemref':continue
                name=(base/items[spine.attrib['idref']]).as_posix()
                raw=z.read(name)
                try: tree=ET.fromstring(raw)
                except ET.ParseError:
                    parser=TolerantBlocks();parser.feed(raw.decode('utf-8-sig'));parser.close()
                    if not parser.blocks:raise ValueError(f'No visible blocks in malformed HTML: {name}')
                    for n,t in enumerate(parser.blocks,1):yield f'{name}#block-{n}',t
                    continue
                body=next((e for e in tree.iter() if e.tag.split('}')[-1]=='body'),tree)
                # Use topmost block nodes so nested paragraphs are not duplicated.
                blocks=[]
                def visit(e):
                    tag=e.tag.split('}')[-1]
                    if tag in ('script','style','nav'): return
                    if tag in ('p','h1','h2','h3','h4','h5','h6','li','pre'):
                        text=' '.join(' '.join(e.itertext()).split())
                        if text: blocks.append(text)
                    else:
                        for child in e:visit(child)
                visit(body)
                if not blocks: blocks=[' '.join(' '.join(body.itertext()).split())]
                for n,t in enumerate(blocks,1):
                    if t:yield f'{name}#block-{n}', t
    else:raise ValueError('Pilot supports TXT and EPUB only; convert PDF with a validated extractor first')

def chunk_blocks(blocks,max_words=350,max_chars=900):
    for locator,text in blocks:
        if re.search(r'[\u3400-\u9fff]',text):
            for offset in range(0,len(text),max_chars):
                yield locator+';offset_unit=character',offset,text[offset:offset+max_chars]
        else:
            words=text.split()
            for offset in range(0,len(words),max_words):
                yield locator,offset,' '.join(words[offset:offset+max_words])

def build(catalog,db):
    books=json.loads(Path(catalog).read_text()); rows=[]; seen=set()
    for book in books:
        if not (book.get('rights_cleared') or book.get('usage_scope')=='user_supplied_private_analysis'):raise ValueError(f"Rights not cleared: {book['id']}")
        if book['id'] in seen:raise ValueError('Duplicate book ID')
        seen.add(book['id']); path=Path(book['path'])
        if not path.is_absolute():path=Path(catalog).parent/path
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if book.get('sha256') and book['sha256']!=sha:raise ValueError('Source hash mismatch')
        for n,(loc,offset,text) in enumerate(chunk_blocks(eligible_blocks(extract(path),book.get('exclude_documents',[]))),1):
            rows.append((f"{book['id']}:{n:05}",book['id'],book['title'],loc,offset,text,sha))
    if not rows:raise ValueError('No text extracted')
    counts=[collections.Counter(terms(r[5])) for r in rows]; df=collections.Counter()
    for c in counts:df.update(c.keys())
    idf={t:math.log((1+len(rows))/(1+n))+1 for t,n in df.items()}
    vectors=[]
    for c in counts:
        v={t:(1+math.log(n))*idf[t] for t,n in c.items()}; norm=math.sqrt(sum(x*x for x in v.values()))
        vectors.append({t:x/norm for t,x in v.items()} if norm else {})
    out=Path(db); out.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(out)
    with con:
        con.execute('DROP TABLE IF EXISTS chunks'); con.execute('DROP TABLE IF EXISTS metadata')
        con.execute('CREATE TABLE chunks(id TEXT PRIMARY KEY,book_id TEXT,title TEXT,locator TEXT,word_offset INTEGER,text TEXT,source_sha256 TEXT,vector TEXT)')
        con.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
        con.executemany('INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)',[r+(json.dumps(v,sort_keys=True),) for r,v in zip(rows,vectors)])
        con.executemany('INSERT INTO metadata VALUES(?,?)',[('idf',json.dumps(idf,sort_keys=True)),('method','tfidf-cosine-cjk-ngram-v2'),('book_count',str(len(books)))])
    con.close(); return {'books':len(books),'chunks':len(rows),'vocabulary':len(idf),'method':'TF-IDF cosine (lexical, not neural semantic)'}

def search(db,query,k=5,min_score=0.035,min_coverage=0.60):
    con=sqlite3.connect(f'file:{Path(db).absolute()}?mode=ro',uri=True)
    method=con.execute("SELECT value FROM metadata WHERE key='method'").fetchone()[0]
    if method!='tfidf-cosine-cjk-ngram-v2':
        con.close();raise ValueError('Rebuild index for v2 tokenizer')
    idf=json.loads(con.execute("SELECT value FROM metadata WHERE key='idf'").fetchone()[0])
    c=collections.Counter(terms(query)); v={t:(1+math.log(n))*idf[t] for t,n in c.items() if t in idf}; norm=math.sqrt(sum(x*x for x in v.values()))
    if not norm:con.close();return []
    v={t:x/norm for t,x in v.items()}; result=[]
    for row in con.execute('SELECT * FROM chunks'):
        vec=json.loads(row[7]); score=sum(x*vec.get(t,0) for t,x in v.items())
        coverage=sum(1 for t in c if t in vec)/len(c)
        if score>=min_score and coverage>=min_coverage:result.append(dict(zip(['id','book_id','title','locator','word_offset','text','source_sha256'],row[:7]),score=round(score,6),query_term_coverage=round(coverage,4)))
    con.close(); return sorted(result,key=lambda r:(-r['score'],r['id']))[:k]

if __name__=='__main__':
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
    b=s.add_parser('build');b.add_argument('catalog');b.add_argument('db')
    q=s.add_parser('query');q.add_argument('db');q.add_argument('query');q.add_argument('--top',type=int,default=5)
    a=p.parse_args();print(json.dumps(build(a.catalog,a.db) if a.cmd=='build' else search(a.db,a.query,a.top),ensure_ascii=False,indent=2))
