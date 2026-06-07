"""
15 个 Benchmark 任务，分三级难度。

L1 (5个): 0-1 个外部依赖
L2 (6个): 2-3 个外部依赖
L3 (4个): 4+ 个外部依赖，或涉及版本敏感场景
"""

from .task_definitions import BenchmarkTask, TaskRegistry

registry = TaskRegistry()

# ═══════════════════════════════════════════════════════════
# L1: 基础任务（5个）—— 0-1 个外部依赖
# ═══════════════════════════════════════════════════════════

registry.register(BenchmarkTask(
    id="T1",
    prompt="读取 data.csv 文件，计算 age 列的平均值和标准差",
    code='''
import csv
import math

# 模拟 CSV 数据（无外部文件依赖）
data = """name,age,city
Alice,25,Beijing
Bob,30,Shanghai
Charlie,35,Guangzhou
Diana,28,Shenzhen
Eve,32,Hangzhou"""

reader = csv.DictReader(data.splitlines())
ages = [int(row["age"]) for row in reader]
mean_age = sum(ages) / len(ages)
variance = sum((a - mean_age) ** 2 for a in ages) / len(ages)
std_age = math.sqrt(variance)
print(f"Mean age: {mean_age:.1f}")
print(f"Std age: {std_age:.1f}")
''',
    difficulty=1,
    expected_deps=[],
    category="data",
))

registry.register(BenchmarkTask(
    id="T2",
    prompt="生成 1000 个正态分布随机数，绘制直方图并保存为 histogram.png",
    code='''
import random
import math

# 用 Box-Muller 方法生成正态分布随机数（零依赖）
def normal_random(mu=0, sigma=1):
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    return mu + z * sigma

samples = [normal_random(0, 1) for _ in range(1000)]
mean_val = sum(samples) / len(samples)
variance = sum((x - mean_val) ** 2 for x in samples) / len(samples)
std_val = math.sqrt(variance)

# 构建 ASCII 直方图（无依赖）
hist = [0] * 10
for s in samples:
    idx = min(int((s + 4) / 0.8), 9)  # -4 到 4 范围分 10 个 bin
    if idx >= 0:
        hist[idx] += 1

print("Histogram of normal random samples:")
max_count = max(hist)
for i, count in enumerate(hist):
    bar = "#" * int(count / max_count * 40)
    print(f"  bin {i:2d}: {bar} ({count})")
print(f"Mean: {mean_val:.3f}, Std: {std_val:.3f}")
''',
    difficulty=1,
    expected_deps=[],
    category="data",
))

registry.register(BenchmarkTask(
    id="T3",
    prompt="发送 HTTP GET 请求到 https://httpbin.org/json 并解析返回的 JSON",
    code='''
import urllib.request
import json

url = "https://httpbin.org/json"
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print("Status: OK")
        print(f"Content type: {type(data).__name__}")
        if "slideshow" in data:
            print(f"Keys: {list(data['slideshow'].keys())}")
        print("JSON parsed successfully")
except Exception as e:
    print(f"Error: {e}")
''',
    difficulty=1,
    expected_deps=[],
    category="web",
))

registry.register(BenchmarkTask(
    id="T4",
    prompt="遍历当前目录，找出所有 .py 文件并统计它们的总行数",
    code='''
import os
import glob

# 查找所有 .py 文件
py_files = []
for root, dirs, files in os.walk("."):
    # 跳过隐藏目录
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    for f in files:
        if f.endswith(".py"):
            py_files.append(os.path.join(root, f))

print(f"Found {len(py_files)} .py files")

total_lines = 0
for fpath in py_files:
    try:
        with open(fpath) as f:
            lines = len(f.readlines())
            total_lines += lines
            if lines > 0:
                print(f"  {fpath}: {lines} lines")
    except Exception:
        pass

print(f"Total lines: {total_lines}")
''',
    difficulty=1,
    expected_deps=[],
    category="filesystem",
))

registry.register(BenchmarkTask(
    id="T5",
    prompt="用正则表达式从一个文本中提取所有 email 地址和 URL",
    code='''
import re

text = """
Contact us at support@example.com or sales@company.org.
Visit our website at https://www.example.com/page?id=123
or check docs at http://docs.example.org/intro.
You can also email admin@test.net.
Invalid: @nouser.com, user@, ftp://archive.example.com
"""

# 提取 email
email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"
emails = re.findall(email_pattern, text)
print("Emails found:")
for e in emails:
    print(f"  {e}")

# 提取 URL
url_pattern = r"https?://[a-zA-Z0-9./?=_%+-]+"
urls = re.findall(url_pattern, text)
print("URLs found:")
for u in urls:
    print(f"  {u}")

print(f"\\nTotal: {len(emails)} emails, {len(urls)} URLs")
''',
    difficulty=1,
    expected_deps=[],
    category="text",
))

# ═══════════════════════════════════════════════════════════
# L2: 中等任务（6个）—— 2-3 个外部依赖
# ═══════════════════════════════════════════════════════════

registry.register(BenchmarkTask(
    id="T6",
    prompt="从 https://httpbin.org/json 获取数据，用 pandas 做统计分析",
    code='''
import pandas as pd
import requests
import json

# 模拟从 API 获取数据（避免网络依赖影响可复现性）
# 用 requests 获取，但回退到硬编码数据
try:
    resp = requests.get("https://httpbin.org/json", timeout=5)
    data = resp.json()
except Exception:
    data = {"slideshow": {"title": "Sample", "author": "Test"}}

# 构建 DataFrame
records = [
    {"product": "A", "sales": 100, "region": "North"},
    {"product": "B", "sales": 200, "region": "South"},
    {"product": "A", "sales": 150, "region": "East"},
    {"product": "C", "sales": 300, "region": "North"},
    {"product": "B", "sales": 250, "region": "West"},
    {"product": "A", "sales": 120, "region": "South"},
]
df = pd.DataFrame(records)
print("DataFrame:")
print(df)
print()

# 统计分析
print("=== Summary Statistics ===")
print(df.groupby("product")["sales"].agg(["sum", "mean", "count"]))
print()
print("=== By Region ===")
print(df.groupby("region")["sales"].sum().sort_values(ascending=False))
''',
    difficulty=2,
    expected_deps=["pandas", "requests"],
    category="data",
))

registry.register(BenchmarkTask(
    id="T7",
    prompt="生成一个带标题、坐标轴标签和图例的折线图，保存为 PNG",
    code='''
import matplotlib
matplotlib.use("Agg")  # 非交互后端，无需 display
import matplotlib.pyplot as plt
import numpy as np

# 生成数据
x = np.linspace(0, 10, 100)
y1 = np.sin(x)
y2 = np.cos(x)

# 绘图
plt.figure(figsize=(8, 4))
plt.plot(x, y1, label="sin(x)", linewidth=2)
plt.plot(x, y2, label="cos(x)", linewidth=2, linestyle="--")
plt.title("Sine and Cosine Functions")
plt.xlabel("x")
plt.ylabel("y")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()

# 保存
plt.savefig("test_plot.png", dpi=100)
print("Plot saved to test_plot.png")
print(f"Data points: {len(x)}")
print(f"sin range: [{y1.min():.2f}, {y1.max():.2f}]")
print(f"cos range: [{y2.min():.2f}, {y2.max():.2f}]")
''',
    difficulty=2,
    expected_deps=["matplotlib", "numpy"],
    category="data",
))

registry.register(BenchmarkTask(
    id="T8",
    prompt="爬取一篇文章，提取所有表格数据并用 pandas 导出为 CSV",
    code='''
import pandas as pd
from bs4 import BeautifulSoup

# 模拟 HTML 页面（避免网络依赖）
html = """
<html><body>
<h1>Sales Report</h1>
<table>
  <tr><th>Month</th><th>Revenue</th><th>Cost</th></tr>
  <tr><td>Jan</td><td>10000</td><td>7000</td></tr>
  <tr><td>Feb</td><td>12000</td><td>8000</td></tr>
  <tr><td>Mar</td><td>15000</td><td>9000</td></tr>
  <tr><td>Apr</td><td>11000</td><td>7500</td></tr>
  <tr><td>May</td><td>13000</td><td>8500</td></tr>
  <tr><td>Jun</td><td>16000</td><td>10000</td></tr>
</table>
<table>
  <tr><th>Product</th><th>Units</th><th>Price</th></tr>
  <tr><td>A</td><td>100</td><td>10</td></tr>
  <tr><td>B</td><td>200</td><td>20</td></tr>
</table>
</body></html>
"""

soup = BeautifulSoup(html, "html.parser")
tables = soup.find_all("table")
print(f"Found {len(tables)} tables")

for i, table in enumerate(tables):
    rows = table.find_all("tr")
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    data = [[td.get_text(strip=True) for td in row.find_all(["th", "td"])] for row in rows[1:]]

    df = pd.DataFrame(data, columns=headers)
    print(f"\\nTable {i+1}: {headers}")
    print(df)

    # 导出
    csv_name = f"table_{i+1}.csv"
    df.to_csv(csv_name, index=False)
    print(f"  Saved to {csv_name}")

print("\\nAll tables extracted and saved")
''',
    difficulty=2,
    expected_deps=["pandas", "beautifulsoup4"],
    category="web",
))

registry.register(BenchmarkTask(
    id="T9",
    prompt="生成一段文本的词云图并保存为图片",
    code='''
from wordcloud import WordCloud
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

text = """
Python is a programming language that lets you work quickly
and integrate systems more effectively. Python is powerful and fast.
It plays well with others and runs everywhere. Python is friendly
and easy to learn. The Python community is welcoming and diverse.
Data science machine learning artificial intelligence Python.
"""

# 生成词云
wc = WordCloud(
    width=800,
    height=400,
    background_color="white",
    max_words=50,
    collocations=False,
).generate(text)

# 保存
wc.to_file("wordcloud.png")
print("Word cloud saved to wordcloud.png")

# 输出词频信息
freq = sorted(wc.words_.items(), key=lambda x: x[1], reverse=True)
print("\\nTop 10 words:")
for word, count in freq[:10]:
    print(f"  {word}: {count}")
''',
    difficulty=2,
    expected_deps=["wordcloud", "matplotlib"],
    category="text",
))

registry.register(BenchmarkTask(
    id="T10",
    prompt="读取 YAML 配置文件，修改其中某些值后输出为 JSON",
    code='''
import yaml
import json

# 模拟 YAML 配置文件
yaml_content = """
server:
  host: "0.0.0.0"
  port: 8080
  workers: 4

database:
  driver: "postgresql"
  host: "db.example.com"
  port: 5432
  name: "myapp"
  pool:
    min: 5
    max: 20

features:
  caching: true
  rate_limiting: true
  logging_level: "info"

apps:
  - name: web
    replicas: 3
  - name: worker
    replicas: 2
  - name: scheduler
    replicas: 1
"""

config = yaml.safe_load(yaml_content)
print("=== Original Config ===")
print(json.dumps(config, indent=2))

# 修改配置
config["server"]["port"] = 9090
config["database"]["pool"]["max"] = 50
config["features"]["logging_level"] = "debug"
config["apps"].append({"name": "monitor", "replicas": 1})

print("\\n=== Modified Config (JSON) ===")
output = json.dumps(config, indent=2)
print(output)

print(f"\\nApps: {[a['name'] for a in config['apps']]}")
print(f"Total replicas: {sum(a['replicas'] for a in config['apps'])}")
''',
    difficulty=2,
    expected_deps=["pyyaml"],
    category="config",
))

registry.register(BenchmarkTask(
    id="T11",
    prompt="创建一个 DataFrame 并导出为 Excel 文件（含多个 sheet）",
    code='''
import pandas as pd

# Sheet 1: Sales
sales_df = pd.DataFrame({
    "Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
    "Sales": [10000, 12000, 15000, 11000, 13000, 16000],
    "Target": [12000, 12000, 12000, 14000, 14000, 14000],
})
sales_df["Achieved"] = (sales_df["Sales"] / sales_df["Target"] * 100).round(1)
print("=== Sales ===")
print(sales_df)

# Sheet 2: Products
products_df = pd.DataFrame({
    "Product": ["A", "B", "C", "D"],
    "Price": [10, 20, 30, 40],
    "Stock": [100, 200, 150, 80],
})
products_df["Value"] = products_df["Price"] * products_df["Stock"]
print("\\n=== Products ===")
print(products_df)

# 导出到 Excel
with pd.ExcelWriter("report.xlsx", engine="openpyxl") as writer:
    sales_df.to_excel(writer, sheet_name="Sales", index=False)
    products_df.to_excel(writer, sheet_name="Products", index=False)

print("\\nExcel report saved to report.xlsx")
print(f"Total sales: ${sales_df['Sales'].sum():,}")
print(f"Total product value: ${products_df['Value'].sum():,}")
''',
    difficulty=2,
    expected_deps=["pandas", "openpyxl"],
    category="data",
))

# ═══════════════════════════════════════════════════════════
# L3: 困难任务（4个）—— 4+ 个外部依赖
# ═══════════════════════════════════════════════════════════

registry.register(BenchmarkTask(
    id="T12",
    prompt="加载一张图片，用 NumPy 做灰度转换和边缘检测，用 PIL 保存结果",
    code='''
import numpy as np

# 创建模拟图片（400x300 RGB，渐变色方格图案）
# 避免需要实际文件
width, height = 400, 300
img = np.zeros((height, width, 3), dtype=np.uint8)

# 生成方格图案
for y in range(height):
    for x in range(width):
        r = int(255 * x / width)  # 水平红渐变
        g = int(255 * y / height)  # 垂直绿渐变
        b = int(255 * (x + y) / (width + height))  # 对角蓝渐变
        img[y, x] = [r, g, b]

print(f"Image shape: {img.shape}")
print(f"Color range: [{img.min()}, {img.max()}]")

# 灰度转换
gray = (img[:, :, 0] * 0.299 + img[:, :, 1] * 0.587 + img[:, :, 2] * 0.114).astype(np.uint8)
print(f"Grayscale shape: {gray.shape}")
print(f"Gray range: [{gray.min()}, {gray.max()}]")

# 简单边缘检测（Sobel 算子）
from scipy import ndimage
sobel_x = ndimage.sobel(gray.astype(float), axis=0)
sobel_y = ndimage.sobel(gray.astype(float), axis=1)
edges = np.hypot(sobel_x, sobel_y)
edges = (edges / edges.max() * 255).astype(np.uint8)
print(f"Edges shape: {edges.shape}")
print(f"Edge intensity range: [{edges.min()}, {edges.max()}]")

print("Image processing complete")

# 保存（如果有 PIL）
try:
    from PIL import Image
    Image.fromarray(img).save("test_original.png")
    Image.fromarray(gray).save("test_gray.png")
    Image.fromarray(edges).save("test_edges.png")
    print("Images saved (original, gray, edges)")
except ImportError:
    print("Pillow not installed; skipping PNG save. NumPy arrays processed successfully.")
''',
    difficulty=3,
    expected_deps=["numpy", "scipy", "pillow"],
    category="image",
))

registry.register(BenchmarkTask(
    id="T13",
    prompt="用 scikit-learn 训练一个简单的线性回归模型，预测房价，输出 MSE 和 R²",
    code='''
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score

# 生成模拟房价数据
np.random.seed(42)
n_samples = 200

area = np.random.normal(100, 30, n_samples)       # 面积 (㎡)
rooms = np.random.randint(1, 6, n_samples)         # 房间数
age = np.random.normal(15, 10, n_samples)          # 房龄 (年)
floor = np.random.randint(1, 30, n_samples)        # 楼层

# 房价 = 面积*2万 + 房间*5万 - 房龄*0.5万 + 楼层*0.3万 + 常数 + 噪声
price = (area * 2 + rooms * 5 - age * 0.5 + floor * 0.3 + 50
         + np.random.normal(0, 10, n_samples))

# 构建 DataFrame
df = pd.DataFrame({
    "area": area,
    "rooms": rooms,
    "age": age,
    "floor": floor,
    "price": price,
})
print("=== Dataset Sample ===")
print(df.head())
print(f"\\nDataset shape: {df.shape}")

# 分割
X = df[["area", "rooms", "age", "floor"]]
y = df["price"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 训练
model = LinearRegression()
model.fit(X_train, y_train)
print(f"\\nCoefficients: {dict(zip(X.columns, model.coef_.round(3)))}")
print(f"Intercept: {model.intercept_:.2f}")

# 评估
y_pred = model.predict(X_test)
mse = mean_squared_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)
print(f"\\n=== Model Performance ===")
print(f"MSE: {mse:.2f}")
print(f"R²: {r2:.4f}")
print(f"RMSE: {np.sqrt(mse):.2f} 万元")
assert r2 > 0.5, f"R² should be reasonable, got {r2:.4f}"
print("Model training and evaluation complete")
''',
    difficulty=3,
    expected_deps=["numpy", "pandas", "scikit-learn"],
    category="ml",
))

registry.register(BenchmarkTask(
    id="T14",
    prompt="对一段文本做预处理（分词、去停用词、词形还原），然后计算 TF-IDF 矩阵",
    code='''
import pandas as pd
import numpy as np
import re

# ═══ 文本预处理（零依赖实现，不依赖 nltk/sklearn 的内置资源） ═══

# 模拟文档集合
documents = [
    "Python is a great programming language for data science and machine learning",
    "Machine learning with Python is powerful for building predictive models",
    "Data science involves statistics, visualization, and machine learning techniques",
    "Python libraries like scikit-learn make machine learning accessible to everyone",
    "Deep learning is a subset of machine learning that uses neural networks",
    "Natural language processing helps computers understand human language and text",
    "Python ecosystem includes numpy pandas and scikit-learn for data science workflows",
]

# 简单停用词表
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "and", "but", "or", "not", "no", "that", "this", "it", "its",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "they", "them",
}

def preprocess(text):
    """简单预处理：分词 + 小写 + 去停用词 + 去标点 + 去短词。"""
    text = text.lower()
    text = re.sub(r"[^a-z\\s]", " ", text)
    tokens = text.split()
    tokens = [t for t in tokens if t not in STOP_WORDS and len(t) > 2]
    return tokens

# 预处理所有文档
processed = [preprocess(doc) for doc in documents]
print("=== Preprocessed Documents ===")
for i, tokens in enumerate(processed):
    print(f"Doc {i+1}: {tokens}")

# ═══ TF-IDF 计算 ═══
# 词汇表
vocab = sorted({token for doc in processed for token in doc})
print(f"\\nVocabulary size: {len(vocab)}")

# TF 矩阵
tf_matrix = np.zeros((len(documents), len(vocab)))
for i, doc in enumerate(processed):
    for token in doc:
        j = vocab.index(token)
        tf_matrix[i, j] += 1
    # 归一化
    if tf_matrix[i].sum() > 0:
        tf_matrix[i] /= tf_matrix[i].sum()

# IDF
doc_count = len(documents)
df = np.array([sum(1 for doc in processed if term in doc) for term in vocab])
idf = np.log((1 + doc_count) / (1 + df)) + 1

# TF-IDF
tfidf = tf_matrix * idf

# 输出结果
print("\\n=== Top TF-IDF Terms per Document ===")
for i in range(len(documents)):
    top_indices = np.argsort(tfidf[i])[::-1][:5]
    top_terms = [(vocab[j], round(tfidf[i, j], 3)) for j in top_indices if tfidf[i, j] > 0]
    print(f"Doc {i+1}: {top_terms}")

# 用 pandas 展示矩阵
top_n = 15
df_tfidf = pd.DataFrame(
    tfidf[:, :top_n],
    index=[f"Doc{i+1}" for i in range(len(documents))],
    columns=vocab[:top_n],
)
print(f"\\nTF-IDF Matrix (first {top_n} terms):")
print(df_tfidf.round(2))
''',
    difficulty=3,
    expected_deps=["numpy", "pandas"],
    category="text",
))

registry.register(BenchmarkTask(
    id="T15",
    prompt="实现一个多步骤数据处理管道：获取数据 → 清洗 → 分析 → 可视化",
    code='''
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats

# ═══ Step 1: 获取数据 ═══
np.random.seed(42)
n = 500

# 模拟电商订单数据
dates = pd.date_range("2024-01-01", periods=n, freq="h")
products = np.random.choice(["A", "B", "C", "D"], n, p=[0.3, 0.25, 0.25, 0.2])
quantities = np.random.poisson(2, n) + 1
prices = np.where(
    products == "A", 10,
    np.where(products == "B", 20,
    np.where(products == "C", 30, 40))
)
amounts = quantities * prices
regions = np.random.choice(["North", "South", "East", "West"], n, p=[0.3, 0.2, 0.3, 0.2])

df = pd.DataFrame({
    "datetime": dates,
    "product": products,
    "quantity": quantities,
    "price": prices,
    "amount": amounts,
    "region": regions,
})
print(f"=== Raw Data: {len(df)} orders ===")
print(df.head())

# ═══ Step 2: 数据清洗 ═══
# 注入一些异常值
df.loc[10, "amount"] = df["amount"].max() * 100  # 极端值
df.loc[20, "quantity"] = -5                      # 不可能的值

print(f"\\n Before cleaning: amount range [{df['amount'].min():.0f}, {df['amount'].max():.0f}]")

# 清洗：去除负值和极端离群点
df = df[df["quantity"] > 0]
z_scores = np.abs(scipy_stats.zscore(df["amount"]))
df = df[z_scores < 3]
print(f"After cleaning: {len(df)} orders (removed {n - len(df)} outliers)")
print(f"Amount range: [{df['amount'].min():.0f}, {df['amount'].max():.0f}]")

# ═══ Step 3: 数据分析 ═══
print("\\n=== Sales Analysis ===")
print(f"Total revenue: ${df['amount'].sum():,.0f}")
print(f"Avg order value: ${df['amount'].mean():.2f}")
print(f"Total orders: {len(df)}")

print("\\n=== By Product ===")
product_stats = df.groupby("product").agg(
    total_amount=("amount", "sum"),
    avg_amount=("amount", "mean"),
    orders=("amount", "count"),
).round(2)
print(product_stats)

print("\\n=== By Region ===")
region_stats = df.groupby("region").agg(
    total_revenue=("amount", "sum"),
    avg_order=("amount", "mean"),
    orders=("amount", "count"),
).round(2).sort_values("total_revenue", ascending=False)
print(region_stats)

# ═══ Step 4: 可视化 ═══
fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# 销售额趋势
daily = df.set_index("datetime").resample("D")["amount"].sum()
axes[0, 0].plot(daily.index, daily.values, marker="o", markersize=2)
axes[0, 0].set_title("Daily Revenue")
axes[0, 0].set_ylabel("Revenue ($)")
axes[0, 0].tick_params(axis="x", rotation=45)

# 产品分布
product_counts = df["product"].value_counts()
axes[0, 1].bar(product_counts.index, product_counts.values, color=["#ff6b6b", "#4ecdc4", "#45b7d1", "#96ceb4"])
axes[0, 1].set_title("Orders by Product")
axes[0, 1].set_ylabel("Count")

# 地区分布
region_revenue = df.groupby("region")["amount"].sum().sort_values(ascending=False)
axes[1, 0].pie(region_revenue.values, labels=region_revenue.index, autopct="%1.1f%%")
axes[1, 0].set_title("Revenue by Region")

# 订单金额分布
axes[1, 1].hist(df["amount"], bins=30, edgecolor="black", alpha=0.7)
axes[1, 1].set_title("Order Amount Distribution")
axes[1, 1].set_xlabel("Amount ($)")
axes[1, 1].set_ylabel("Frequency")

plt.tight_layout()
plt.savefig("sales_dashboard.png", dpi=120)
print("\\nDashboard saved to sales_dashboard.png")
print("Pipeline complete: extract → clean → analyze → visualize")
''',
    difficulty=3,
    expected_deps=["numpy", "pandas", "matplotlib", "scipy"],
    category="pipeline",
))

# ── 便捷访问 ──────────────────────────────────────────────

def get_all_tasks() -> list[BenchmarkTask]:
    return registry.all()

def get_tasks_by_difficulty(d: int) -> list[BenchmarkTask]:
    return registry.list_by_difficulty(d)

def get_task(task_id: str) -> BenchmarkTask:
    return registry.get(task_id)
