from bs4 import BeautifulSoup
import os
import re
import csv
import urllib.parse

# 从 CSV 中读取图片ID映射表
def load_image_map():
    image_map = {}
    for filename in os.listdir("."):
        if filename.endswith("_steam_guide_images.csv"):
            with open(filename, newline='', encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    image_map[row['title']] = row['id']
            break
    return image_map

image_map = load_image_map()

def convert_html_to_bbcode(html_content):
    from bs4 import NavigableString

    soup = BeautifulSoup(html_content, "html.parser")
    article = soup.find("article")
    if not article:
        return "[Error] 正文部分未找到"

    skip_nodes = set()

    def parse_node(node):
        if node in skip_nodes:
            return ""

        if isinstance(node, NavigableString):
            return node.string or ""

        tag = node.name.lower()
        contents = "".join(parse_node(c) for c in node.contents)

        if tag == "p":
            return f"{contents.strip()}\n"

        if tag in ["h1", "h2", "h3"]:
            return f"[{tag}]{contents.strip()}[/{tag}]\n"

        if tag in ["strong", "b"]:
            return f"[b]{contents}[/b]"

        if tag in ["em", "i"]:
            return f"[i]{contents}[/i]"

        if tag == "span" and "border-bottom" in node.get("style", ""):
            return f"[u]{contents}[/u]"

        if tag == "del":
            return f"[strike]{contents}[/strike]"

        if tag == "mark":
            return f"[spoiler]{contents}[/spoiler]"

        if tag == "blockquote":
            return f"[quote]{contents}[/quote]\n"

        if tag == "hr":
            return "[hr]\n"

        if tag == "code":
            return contents

        if tag == "pre":
            return f"[code]{contents}[/code]\n"

        if tag == "a":
            # 跳过 <a> 包裹图片的情况
            if node.find("img"):
                return contents
            href = node.get("href", "#")
            return f"[url={href}]{contents}[/url]"

        if tag in ["ul"]:
            items = "".join(f"[*]{parse_node(li)}" for li in node.find_all("li", recursive=False))
            return f"[list]{items}[/list]\n"
        
        if tag in ["ol"]:
            items = "".join(f"[*]{parse_node(li)}" for li in node.find_all("li", recursive=False))
            return f"[olist]{items}[/olist]\n"

        if tag == "table":
            rows = []
            for tr in node.find_all("tr"):
                cells = []
                for cell in tr.find_all(["th", "td"]):
                    cell_tag = "th" if cell.name == "th" else "td"
                    cells.append(f"[{cell_tag}]{parse_node(cell)}[/{cell_tag}]")
                rows.append(f"[tr]{''.join(cells)}[/tr]")
            return f"[table]{''.join(rows)}[/table]\n"

        if tag == "figure":
            img = node.find("img")
            if not img:
                return ""

            src = img.get("src", "")
            filename = os.path.basename(urllib.parse.unquote(src)) #解码
            preview_id = image_map.get(filename)
            if not preview_id:
                return f"[img]{src}[/img]"

            # 检查 <figure> 后是否有尺寸说明 <p>
            next_tag = node.find_next_sibling()
            while next_tag and (
                isinstance(next_tag, NavigableString) or
                (next_tag.name == "p" and next_tag.get_text(strip=True) == "")
            ):
                next_tag = next_tag.find_next_sibling()

            size_char = None
            if next_tag and next_tag.name == "p":
                size_text = next_tag.get_text(strip=True).upper()
                if size_text in ["M", "L"]:
                    size_char = size_text
                    skip_nodes.add(next_tag)  # 避免输出尺寸说明

            if size_char == "M":
                size = "sizeThumb"
            elif size_char == "L":
                size = "sizeFull"
            else:
                size = "sizeOriginal"

            return f"[previewimg={preview_id};{size},inline;{filename}][/previewimg]\n"

        return contents

    result = [parse_node(child) for child in article.children]
    return "\n".join(line.strip() for line in result if line.strip())



def post_process_bbcode(bbcode_text, image_map):
    import urllib.parse

    # 替换 [td]filename[/td] 为图片 BBCode
    def image_replacer(match):
        raw_filename = match.group(1)
        filename = urllib.parse.unquote(raw_filename)
        image_id = image_map.get(filename)
        if image_id:
            return f"[td][previewimg={image_id};sizeThumb,inline;{filename}][/previewimg][/td]"
        else:
            return match.group(0)

    bbcode_text = re.sub(r"\[td\]([^\]]+?)\[/td\]", image_replacer, bbcode_text, flags=re.IGNORECASE)

    # 合并相邻的相同列表块
    def merge_lists(bbcode_text, list_tag):
        pattern = re.compile(rf"\[{list_tag}\]((?:\[\*\].*?)+)\[/{list_tag}\]", re.DOTALL)
        matches = pattern.findall(bbcode_text)

        merged = []
        last_end = 0
        result = ""

        # 找出所有匹配的位置
        for match in re.finditer(pattern, bbcode_text):
            start, end = match.span()
            merged.append((start, end, match.group(1)))

        i = 0
        while i < len(merged):
            start, end, content = merged[i]
            j = i + 1
            # 合并后续连续的列表
            while j < len(merged) and merged[j][0] == merged[j - 1][1] + 1:
                content += merged[j][2]
                end = merged[j][1]
                j += 1
                
            content = re.sub(r'\[\*\](.*?)', r'\n    [*]\1', content)
            result += bbcode_text[last_end:start]
            result += f"[{list_tag}]{content}\n[/{list_tag}]"
            last_end = end
            i = j

        result += bbcode_text[last_end:]
        return result

    # 合并 [olist] 和 [list]
    bbcode_text = merge_lists(bbcode_text, "olist")
    bbcode_text = merge_lists(bbcode_text, "list")

    return bbcode_text


# 替换 HTML 转 BBCode 的主循环
for filename in os.listdir("."):
    if filename.lower().endswith(".html"):
        with open(filename, "r", encoding="utf-8") as f:
            html = f.read()
        bbcode = convert_html_to_bbcode(html)
        bbcode = post_process_bbcode(bbcode, image_map)

        output_filename = os.path.splitext(filename)[0] + ".txt"
        with open(output_filename, "w", encoding="utf-8") as out:
            out.write(bbcode)
        print(f"已转换：{filename} → {output_filename}")

