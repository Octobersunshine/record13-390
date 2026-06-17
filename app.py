import base64
import io
import os
import re
import sys

from flask import Flask, jsonify, request
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

app = Flask(__name__)


def _configure_chinese_font():
    cn_font_keywords = [
        "SimHei", "Microsoft YaHei", "Microsoft YaHei UI", "MS YaHei",
        "PingFang SC", "PingFang HK", "PingFang TC", "Heiti SC", "Heiti TC",
        "Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Sans SC", "Noto Sans TC",
        "Source Han Sans SC", "Source Han Sans CN", "Source Han Sans TC",
        "WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "WenQuanYi",
        "Arial Unicode MS", "SimSun", "STHeiti", "STKaiti", "KaiTi",
    ]

    if sys.platform.startswith("win"):
        win_fonts = [
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\msyh.ttf",
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\msyhbd.ttf",
            r"C:\Windows\Fonts\msyhl.ttc",
            r"C:\Windows\Fonts\simsun.ttc",
        ]
        for fp in win_fonts:
            if os.path.exists(fp):
                try:
                    fm.fontManager.addfont(fp)
                except Exception:
                    pass
    elif sys.platform == "darwin":
        mac_fonts = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/Library/Fonts/Songti.ttc",
        ]
        for fp in mac_fonts:
            if os.path.exists(fp):
                try:
                    fm.fontManager.addfont(fp)
                except Exception:
                    pass
    else:
        linux_font_dirs = [
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts"),
        ]
        for d in linux_font_dirs:
            if os.path.isdir(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith((".ttf", ".ttc", ".otf")):
                            fp = os.path.join(root, f)
                            try:
                                fm.fontManager.addfont(fp)
                            except Exception:
                                pass

    available_names = {f.name for f in fm.fontManager.ttflist}

    matched = []
    for kw in cn_font_keywords:
        for name in available_names:
            if kw.lower() == name.lower() or kw.lower() in name.lower():
                if name not in matched:
                    matched.append(name)

    fallback = [n for n in available_names if any(
        kw.lower() in n.lower() for kw in ["hei", "yahei", "cjk", "chinese", "simsun", "song", "kaiti", "st"]
    ) and n not in matched]
    matched.extend(fallback)

    matched.append("DejaVu Sans")
    matched.append("Arial")

    plt.rcParams["font.sans-serif"] = matched
    plt.rcParams["axes.unicode_minus"] = False

    return matched[0] if matched else "DejaVu Sans"


_active_cn_font = _configure_chinese_font()


def _render(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _validate(payload):
    if not payload or "labels" not in payload or "datasets" not in payload:
        return None, "请求体须包含 labels 和 datasets"
    if not isinstance(payload["labels"], list):
        return None, "labels 须为列表"
    if not isinstance(payload["datasets"], list) or len(payload["datasets"]) == 0:
        return None, "datasets 须为非空列表"
    for ds in payload["datasets"]:
        if "values" not in ds or not isinstance(ds["values"], list):
            return None, "每个 dataset 须包含 values 列表"
    return payload, None


_TIME_PATTERNS = [
    re.compile(r"^\d{4}[-/年.]\s*\d{1,2}([-/月.]\s*\d{1,2}日?)?$"),
    re.compile(r"^\d{4}[-/年.]\s*Q[1-4]$", re.I),
    re.compile(r"^第?[一二三四五六七八九十百千\d]+[季月周日天]$"),
    re.compile(r"^[1-9]\d{0,2}\s*[月日季周]$"),
    re.compile(r"^(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|sep(tember)?|oct(ober)?|nov(ember)?|dec(ember)?)\s*\d*$", re.I),
    re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$"),
]

_CN_NUM_ORDER = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def _is_time_label(labels):
    if len(labels) < 2:
        return False
    str_labels = [str(l).strip() for l in labels]
    matched = sum(1 for l in str_labels if any(p.match(l) for p in _TIME_PATTERNS))
    if matched / len(str_labels) >= 0.7:
        return True
    prefixes = ["Q", "第", "星期", "周"]
    pref_match = sum(1 for l in str_labels if any(l.startswith(p) for p in prefixes))
    if pref_match / len(str_labels) >= 0.7:
        return True
    order_hits = sum(1 for l in str_labels if any(n in l for n in _CN_NUM_ORDER))
    if order_hits / len(str_labels) >= 0.7:
        return True
    return False


def _all_numeric(values):
    try:
        nums = [float(v) for v in values]
        return True, nums
    except (TypeError, ValueError):
        return False, []


def _analyze(payload):
    labels = payload["labels"]
    datasets = payload["datasets"]
    n_labels = len(labels)
    n_series = len(datasets)

    first_values = datasets[0]["values"]
    all_series_values = [v for ds in datasets for v in ds["values"]]
    all_numeric, numeric_all = _all_numeric(all_series_values)
    first_numeric, first_nums = _all_numeric(first_values)

    is_time = _is_time_label(labels)

    all_non_negative = all_numeric and all(v >= 0 for v in numeric_all)
    sum_first = sum(first_nums) if first_numeric else 0
    near_percent = (
        first_numeric and sum_first > 0
        and 90 <= abs(sum_first - 100) <= 110 or (all(v <= 1 for v in first_nums) and 0.9 <= sum_first <= 1.1)
    )

    has_name = any(ds.get("name") for ds in datasets)
    max_val = max(numeric_all) if all_numeric and numeric_all else 0
    min_val = min(numeric_all) if all_numeric and numeric_all else 0
    value_range_ratio = (max_val - min_val) / abs(max_val) if max_val != 0 else 0

    return {
        "n_labels": n_labels,
        "n_series": n_series,
        "is_time": is_time,
        "all_non_negative": all_non_negative,
        "near_percent_partition": near_percent,
        "has_series_name": has_name,
        "value_range_ratio": value_range_ratio,
        "sum_first_series": sum_first,
    }


def recommend_chart(payload):
    analysis = _analyze(payload)
    scores = {"line": 0, "bar": 0, "pie": 0}
    reasons = {"line": [], "bar": [], "pie": []}

    n = analysis["n_labels"]
    ns = analysis["n_series"]

    if analysis["is_time"]:
        scores["line"] += 40
        reasons["line"].append("labels 呈时间/顺序序列，适合展示趋势变化")
    else:
        scores["bar"] += 15
        reasons["bar"].append("labels 为离散分类，适合对比类间数值")

    if ns == 1:
        scores["pie"] += 25
        reasons["pie"].append("仅有一个数据系列，适合展示构成占比")
        if analysis["all_non_negative"]:
            scores["pie"] += 15
            reasons["pie"].append("所有数值非负，可计算占比")
            if 3 <= n <= 8:
                scores["pie"] += 15
                reasons["pie"].append(f"类别数 {n} 在饼图最佳区间（3~8）")
            elif n > 10:
                scores["pie"] -= 20
                reasons["pie"].append(f"类别数 {n} 过多，饼图扇区过密难读")
            if analysis["near_percent_partition"]:
                scores["pie"] += 10
                reasons["pie"].append("数值接近百分比/构成结构")
        else:
            scores["pie"] -= 999
            reasons["pie"].append("存在负值，无法使用饼图")
    else:
        scores["pie"] -= 999
        reasons["pie"].append(f"{ns} 个系列，饼图仅适用于单系列构成")

    if ns >= 2:
        scores["bar"] += 20
        scores["line"] += 20
        reasons["bar"].append(f"{ns} 个系列可分组柱状对比")
        reasons["line"].append(f"{ns} 个系列可多线对比趋势")
        if analysis["has_series_name"]:
            scores["bar"] += 5
            scores["line"] += 5

    if n > 12:
        scores["bar"] -= 15
        scores["line"] += 20
        reasons["line"].append(f"类别数 {n} 较多，折线图更易观察整体走势")
        reasons["bar"].append(f"类别数 {n} 较多，柱状图易拥挤")
    elif 3 <= n <= 10:
        scores["bar"] += 15
        reasons["bar"].append(f"类别数 {n} 在柱状图最佳区间（3~10）")

    if analysis["value_range_ratio"] > 10:
        scores["line"] += 10
        reasons["line"].append("数值跨度大，折线图可清晰展示幅度变化")
    elif analysis["all_non_negative"] and analysis["value_range_ratio"] < 2 and 3 <= n <= 8 and ns == 1:
        scores["pie"] += 5

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_type, best_score = ranked[0]
    second_type, second_score = ranked[1]
    diff = best_score - second_score

    conf = "high" if diff >= 20 else "medium" if diff >= 8 else "low"

    def fmt_reasons(t):
        return [r for r in reasons[t] if not r.startswith("存在负值") and "仅适用" not in r and "过多" not in r and "拥挤" not in r]

    result = {
        "recommended": best_type,
        "confidence": conf,
        "score": best_score,
        "reason": "; ".join(fmt_reasons(best_type)) or "综合特征匹配",
        "alternatives": [
            {"type": t, "score": s, "reason": "; ".join(fmt_reasons(t)) or "综合特征匹配"}
            for t, s in ranked[1:] if s > -500
        ],
        "analysis": analysis,
    }
    return result


@app.route("/chart/recommend", methods=["POST"])
def chart_recommend():
    payload, err = _validate(request.get_json(silent=True))
    if err:
        return jsonify({"error": err}), 400
    return jsonify(recommend_chart(payload))


def _render_line(payload):
    title = payload.get("title", "折线图")
    labels = payload["labels"]
    datasets = payload["datasets"]
    fig, ax = plt.subplots(figsize=(8, 5))
    for ds in datasets:
        name = ds.get("name", "")
        ax.plot(labels, ds["values"], marker="o", label=name)
    ax.set_title(title)
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    return _render(fig)


def _render_bar(payload):
    title = payload.get("title", "柱状图")
    labels = payload["labels"]
    datasets = payload["datasets"]
    n = len(datasets)
    bar_width = 0.7 / n if n > 1 else 0.5
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(labels))
    for i, ds in enumerate(datasets):
        offset = (i - (n - 1) / 2) * bar_width
        name = ds.get("name", "")
        ax.bar([xi + offset for xi in x], ds["values"], width=bar_width, label=name)
    ax.set_title(title)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(True, axis="y", linestyle="--", alpha=0.5)
    return _render(fig)


def _render_pie(payload):
    title = payload.get("title", "饼图")
    labels = payload["labels"]
    values = payload["datasets"][0]["values"]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.set_title(title)
    ax.axis("equal")
    return _render(fig)


_RENDERERS = {"line": _render_line, "bar": _render_bar, "pie": _render_pie}


@app.route("/chart/line", methods=["POST"])
def line_chart():
    payload, err = _validate(request.get_json(silent=True))
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"image_base64": _render_line(payload)})


@app.route("/chart/bar", methods=["POST"])
def bar_chart():
    payload, err = _validate(request.get_json(silent=True))
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"image_base64": _render_bar(payload)})


@app.route("/chart/pie", methods=["POST"])
def pie_chart():
    payload, err = _validate(request.get_json(silent=True))
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"image_base64": _render_pie(payload)})


@app.route("/chart", methods=["POST"])
def chart():
    payload = request.get_json(silent=True)
    if not payload or "chart_type" not in payload:
        return jsonify({"error": "请求体须包含 chart_type (auto/line/bar/pie)"}), 400

    chart_type = payload["chart_type"]
    valid_payload, err = _validate(payload)
    if err:
        return jsonify({"error": err}), 400

    if chart_type == "auto":
        rec = recommend_chart(valid_payload)
        chosen = rec["recommended"]
        return jsonify({
            "image_base64": _RENDERERS[chosen](valid_payload),
            "chart_type_used": chosen,
            "recommend_detail": rec,
        })

    if chart_type not in _RENDERERS:
        return jsonify({"error": f"不支持的 chart_type: {chart_type}，可选 auto/line/bar/pie"}), 400

    return jsonify({"image_base64": _RENDERERS[chart_type](valid_payload)})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
