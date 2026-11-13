import sys,tempfile,json,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from search_books import build,search,extract,chunk_blocks,eligible_blocks
class TestSearch(unittest.TestCase):
 def test_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'a.txt').write_text('Gratitude and action.\n\nImagination and faith.');(p/'b.txt').write_text('Gardens contain flowers and trees.')
   cat=[{'id':'a','title':'A','path':'a.txt','rights_cleared':True},{'id':'b','title':'B','path':'b.txt','rights_cleared':True}]
   (p/'catalog.json').write_text(json.dumps(cat)); r=build(p/'catalog.json',p/'db.sqlite')
   self.assertEqual(r['books'],2);self.assertEqual(r['chunks'],3)
   self.assertEqual(search(p/'db.sqlite','gratitude action')[0]['book_id'],'a')
   self.assertEqual(search(p/'db.sqlite','flowers')[0]['book_id'],'b')
   self.assertEqual(search(p/'db.sqlite','zzzzzz'),[])
   self.assertEqual(build(p/'catalog.json',p/'db.sqlite'),r)
   cat[0]['rights_cleared']=False;(p/'catalog.json').write_text(json.dumps(cat))
   with self.assertRaises(ValueError):build(p/'catalog.json',p/'x.sqlite')
 def test_chunk_coverage(self):
  words=[str(i) for i in range(1001)];chunks=list(chunk_blocks([('p',' '.join(words))]))
  self.assertEqual(' '.join(c[2] for c in chunks),' '.join(words));self.assertEqual(len(chunks),3)
 def test_epub_spine(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.epub'
   with zipfile.ZipFile(p,'w') as z:
    z.writestr('META-INF/container.xml','<container><rootfile full-path="OEBPS/content.opf"/></container>')
    z.writestr('OEBPS/content.opf','<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="b" href="b.xhtml"/><item id="a" href="a.xhtml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>')
    for n in ['a','b']:z.writestr(f'OEBPS/{n}.xhtml',f'<html><body><nav>skip</nav><h1>{n}</h1><p>text {n}</p></body></html>')
   out=list(extract(p));self.assertEqual([x[1] for x in out],['a','text a','b','text b'])
 def test_malformed_user_epub_pattern(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.epub'
   with zipfile.ZipFile(p,'w') as z:
    z.writestr('META-INF/container.xml','<container><rootfile full-path="book.opf"/></container>')
    z.writestr('book.opf','<package mlns="typo"><manifest><item id="a" href="a.html"/></manifest><spine><itemref idref="a"/></spine></package>')
    z.writestr('a.html','<html><head><title>chapter <unescaped></title></head><body><p>第一章</p><p>Visible text.</p></body></html>')
   self.assertEqual([t for _,t in extract(p)],['第一章','Visible text.'])
 def test_chinese_search_and_rejection(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'a.txt').write_text('想像可以協助設計一座花園，先畫出花圃的形狀，再考慮樹木的位置，按照實際的光照條件選擇植物，最後定期記錄生長情況。')
   (p/'catalog.json').write_text(json.dumps([dict(id='a',title='A',path='a.txt',rights_cleared=True)]))
   build(p/'catalog.json',p/'db.sqlite')
   self.assertEqual(search(p/'db.sqlite','想像')[0]['book_id'],'a')
   self.assertEqual(search(p/'db.sqlite','量子計算機'),[])
   self.assertEqual(search(p/'db.sqlite','想'),[])
   self.assertEqual(search(p/'db.sqlite','想像 火箭發動機維修'),[])
 def test_toc_and_chinese_chunks(self):
  blocks=[(f'toc#block-{i}',f'第{i}章 標題') for i in range(1,7)]
  blocks.append(('body#block-1','花園的設計需要考慮光照和植物的生長條件。'*80))
  kept=list(eligible_blocks(blocks));self.assertEqual(len(kept),1)
  chunks=list(chunk_blocks(kept));self.assertTrue(all(len(t)<=900 for _,_,t in chunks))
  self.assertEqual(''.join(t for _,_,t in chunks),kept[0][1])
if __name__=='__main__':unittest.main()
