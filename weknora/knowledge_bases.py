"""WeKnora 里的十个知识库（按资料类型分）和 fabric 各来源进哪个库。不打印任何口令。

    python3 knowledge_bases.py create      # 在 WeKnora 里建库（按名字，已有的不动），编号写进 ~/.config/weknora-kdd/knowledge-bases.json
    python3 knowledge_bases.py configure   # 把 fabric 的索引目标和桥接的来源映射指向这些库（改两份私有配置）

configure 之后重启 datafabric-weknora、datafabric-api、datafabric-clean、datafabric-index。
要改某个库的分块方式：改 KBS 里那一行，在 WeKnora 界面或接口上同步改库的设置（已入库的文档要重新解析才生效）。
要放开抽样：去掉 SAMPLE 里的数字（写 None），configure，再把 fabric 库 index_targets.scanned_seq 置 0。
"""
import json
import os
import sys

import httpx  # fabric 的 .venv 里有：/data/projects/fabric/.venv/bin/python knowledge_bases.py ...

HOME = os.path.expanduser("~/.config/")
IDS = HOME + "weknora-kdd/knowledge-bases.json"
INSTANCE = "datafabric.dev.kdd"
SEPARATORS = ["\n\n", "\n", "。", "；", ". ", "; "]


def chunking(size, overlap=0, parent_child=None):
    """按 Markdown 标题分块（strategy=heading）；没有标题的文档 WeKnora 按 SEPARATORS 依次找断点（段落、行、句子）。"""
    config = {"chunk_size": size, "chunk_overlap": overlap, "separators": SEPARATORS, "strategy": "heading"}
    if parent_child:
        config.update(enable_parent_child=True, parent_chunk_size=parent_child[0], child_chunk_size=parent_child[1])
    return config


# (范围名, 知识库名, 说明, 分块)。短公告、论文摘要尽量一篇一块；长文按标题切成约 1500 字；说明书用父子块
KBS = [
    ("trials", "试验登记", "ClinicalTrials.gov、中国临床试验注册中心的登记", chunking(1500)),
    ("labels", "药品说明书", "openFDA 药品说明书（drug/label）", chunking(500, 0, (4000, 500))),
    ("cn_regulatory", "中国监管公告", "国家药监局、药审中心的公告和信息公开", chunking(4000)),
    ("us_eu_regulatory", "美欧监管公告", "FDA 完整回应函、召回、安全通讯、新闻稿，EMA 新闻", chunking(4000)),
    ("guidance", "政策与指南长文", "药审中心指导原则、药促会政策法规等长文", chunking(1500, 150)),
    ("papers", "已发表论文", "Europe PMC、PubMed 的标题和摘要", chunking(8000)),
    ("preprints", "预印本", "bioRxiv、medRxiv、arXiv q-bio 的标题和摘要", chunking(8000)),
    ("company_reports", "公司定期报告", "SEC 10-K / 10-Q / 20-F，港交所年报和中期报告", chunking(1500, 150)),
    ("company_news", "公司公告与新闻稿", "SEC 8-K、港交所公告、企业新闻稿", chunking(4000)),
    ("leads", "线索", "行业媒体、新闻索引、WHO 疫情通报：只当线索，不是独立证据", chunking(4000)),
]
# 范围名 → {fabric 来源: 抽样上限（最多收几条记录；None = 整个来源都收）}
SAMPLE = {
    "trials": {"clinicaltrials": 60, "chictr": 40},
    "labels": {"fda_api_drug_label": 100},
    "cn_regulatory": {"nmpa": 40, "cde": 40, "cde_xxgk": 20},
    "us_eu_regulatory": {"fda_crl": 25, "fda_api_enforcement": 25, "fda_drug_safety": 20, "fda_press": 20, "ema": 10},
    "guidance": {"cde_zdyz": 70, "phirda_policy": 20, "phirda_healthcare_reform": 10},
    "papers": {"europe_pmc": 50, "pubmed": 50},
    "preprints": {"biorxiv": 35, "medrxiv": 35, "arxiv": 30},
    "company_reports": {"sec_filings": 60, "hkex_reports": 40},
    "company_news": {"sec_8k": 30, "hkex": 30, "roche": 20, "rss_press": 20},
    "leads": {"fiercepharma": 25, "phirda_industry": 20, "phirda_rd": 15, "gdelt_doc": 20, "who_don": 20},
}


def create():
    setup = json.load(open(HOME + "weknora-kdd/weknora-setup.json"))
    client = httpx.Client(base_url="http://127.0.0.1:8080/api/v1", headers={"X-API-Key": setup["api_key"]},
                          timeout=30, trust_env=False)
    existing = {kb["name"]: kb for kb in client.get("/knowledge-bases").json().get("data") or []}
    out = {}
    for scope, name, description, config in KBS:
        kb = existing.get(name)
        if kb is None:
            # 不给 summary_model_id：知识库里不放模型写的摘要（桥接上传时也关了 summary_enabled）
            answer = client.post("/knowledge-bases", json={
                "name": name, "description": description, "type": "document", "chunking_config": config,
                "embedding_model_id": setup["embedding_model_id"],
                "indexing_strategy": {"vector_enabled": True, "keyword_enabled": True, "graph_enabled": False,
                                      "wiki_enabled": False}})
            if answer.status_code not in (200, 201):
                raise SystemExit("建库失败 %s: HTTP %s %s" % (name, answer.status_code, answer.text[:300]))
            kb = answer.json()["data"]
        out[scope] = {"id": kb["id"], "name": name}
        print(scope, kb["id"], name, json.dumps(kb.get("chunking_config"), ensure_ascii=False))
    with open(os.open(IDS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as stream:
        json.dump(out, stream, ensure_ascii=False, indent=1)


def configure():
    kbs = json.load(open(IDS))
    targets, mappings = [], []
    for scope, sources in SAMPLE.items():
        for source, limit in sources.items():
            target = {"source_instance": INSTANCE, "source_id": source, "is_demo": False,
                      "knowledge_base_id": kbs[scope]["id"], "source_scope": scope}
            targets.append(target if limit is None else {**target, "limit": limit})
            mappings.append({"source_instance": INSTANCE, "source_id": source,
                             "knowledge_base_id": kbs[scope]["id"], "scopes": [scope]})
    path = HOME + "datafabric-publication/runtime.env"
    lines = [line for line in open(path).read().split("\n") if not line.startswith("DATAFABRIC_INDEX_TARGETS=")]
    lines.append("DATAFABRIC_INDEX_TARGETS='" + json.dumps(targets, separators=(",", ":")) + "'")
    with open(path, "w") as stream:
        stream.write("\n".join(line for line in lines if line) + "\n")
    path = HOME + "weknora-kdd/runtime.json"
    config = json.load(open(path))
    config["allowed_kb_ids"] = [kb["id"] for kb in kbs.values()]
    config["source_mappings"] = mappings
    with open(path, "w") as stream:
        json.dump(config, stream, ensure_ascii=False, indent=1)
    print("%d 个索引目标，%d 个知识库" % (len(targets), len(kbs)))


if __name__ == "__main__":
    {"create": create, "configure": configure}[sys.argv[1]]()
