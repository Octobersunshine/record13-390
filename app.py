import base64
import io

from flask import Flask, jsonify, request
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

app = Flask(__name__)

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial"]
plt.rcParams["axes.unicode_minus"] = False


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
