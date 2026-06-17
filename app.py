import base64
import io
import os
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


@app.route("/chart/line", methods=["POST"])
def line_chart():
    payload, err = _validate(request.get_json(silent=True))
    if err:
        return jsonify({"error": err}), 400

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

    return jsonify({"image_base64": _render(fig)})


@app.route("/chart/bar", methods=["POST"])
def bar_chart():
    payload, err = _validate(request.get_json(silent=True))
    if err:
        return jsonify({"error": err}), 400

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

    return jsonify({"image_base64": _render(fig)})


@app.route("/chart/pie", methods=["POST"])
def pie_chart():
    payload, err = _validate(request.get_json(silent=True))
    if err:
        return jsonify({"error": err}), 400

    title = payload.get("title", "饼图")
    labels = payload["labels"]
    values = payload["datasets"][0]["values"]

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.set_title(title)
    ax.axis("equal")

    return jsonify({"image_base64": _render(fig)})


@app.route("/chart", methods=["POST"])
def chart():
    payload = request.get_json(silent=True)
    if not payload or "chart_type" not in payload:
        return jsonify({"error": "请求体须包含 chart_type (line/bar/pie)"}), 400

    chart_type = payload["chart_type"]
    dispatch = {"line": line_chart, "bar": bar_chart, "pie": pie_chart}

    if chart_type not in dispatch:
        return jsonify({"error": f"不支持的 chart_type: {chart_type}，可选 line/bar/pie"}), 400

    return dispatch[chart_type]()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
