# 书籍目录与离线检索试点

## 本批实际内容

- `catalog/booklist.csv`：86 条输入书目，分 8 类。它是待核实的阅读目录，不是已取得的 86 本书。书名、作者、分类、主题和备注保留输入信息；主题不是通读后的结论，译名与具体版本仍需核对。部分条目可能表示合集或多册。
- `search/search_books.py`：Python 标准库实现的 EPUB/TXT 提取、分段、SQLite 存储和 TF-IDF 词汇检索代码。
- `search/tests/test_search.py`：7 项合成单元测试，不含真实书籍正文。

本批没有上传书籍正文、提取文本、SQLite 索引、私有分析数据、凭证、全书摘要或课程材料。不声称已经取得、通读或完成 86 本书的知识库。目录备注记录输入中的书目修订，不表示本批重新完成了来源核验。

## 运行

要求 Python 3。无需外部 API、付费调用或模型下载。

```sh
cd search
python -m unittest discover -s tests -v
python search_books.py build catalog.local.json artifacts/pilot.sqlite
python search_books.py query artifacts/pilot.sqlite 'thought character' --top 5
```

`catalog.local.json` 是另行建立的本地 JSON 数组，不是上面的书目 CSV。仅加入已获准使用的文件，例如自创测试文本：

```json
[{"id":"sample","title":"Synthetic example","path":"sample.txt","rights_cleared":true}]
```

`rights_cleared` 必须有真实依据，不能为了运行脚本而设为 true。程序也支持 `usage_scope: user_supplied_private_analysis` 或 `usage_scope: reviewed_private_analysis` 作为私有分析标记；它绝不代表再分发许可。上述示例文件不会随仓库提供。

## 检索限制

这是词汇 TF-IDF 及余弦相似度基线，不是神经语义检索。英文按词，中文按 2/3 字 n-gram；无简繁转换和跨语言语义支持。中文单字查询不支持，同义改写和长问句可能漏召回。

默认 cosine 阈值 0.035、查询词项覆盖阈值 0.60 是实验启发式，不是置信度。空结果不代表书里没有答案。目录和中文短段过滤只适用于实验检索，不能用于证明全书摘要覆盖。PDF/OCR 尚未接入，EPUB 复杂布局、表格、图片和脚注需逐书审核。

结果保留文件定位及 SHA-256；这些定位不是印刷版页码。索引包含原文文本块，适用与原书相同的保密及版权限制。没有真实书籍准确率承诺，7 项合成测试通过不等于完成检索验收。

## 后续验收与发布边界

1. 逐本核对版本、完整性、使用授权和公开再分发权。
2. 权利已核后再决定是否加入公开仓库；私有输入及其索引始终隔离。
3. 对获准的完整文本测试定位、覆盖、召回和拒答，再按章节形成有出处的分析。
4. 每批发布后核验远端文件、提交 SHA 和内容哈希。GitHub 备份仅覆盖实际提交的文件，不等于私有数据已经备份。

`.gitignore` 仅是防误上传提醒，不能代替逐文件审查。禁止把未经许可的书籍或私有索引强制加入版本控制。

## V3 代码更新

英文段落可附带前置章节标题上下文，支持按 locator 排除文本块；Python `search` 函数支持 `book_id` 过滤。标题识别仍是启发式，非完整结构解析。旧索引必须重建，当前方法标识为 `tfidf-cosine-cjk-ngram-v3`。本次更新仅含通用代码与合成测试，不包含私有评测、真实书籍正文或索引。
