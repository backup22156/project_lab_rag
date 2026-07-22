import os
import base64
import json
from dotenv import load_dotenv
from pathlib import Path
import mimetypes

from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image

from openai import OpenAI


load_dotenv()
api_key = os.getenv("PROJECTLAB_OPENAI_KEY")
client = OpenAI(api_key=api_key)
model_basic = "gpt-4.1-mini"
model_foreign = "gpt-5-mini"
max_output_tokens = 12000

def pdftoimage(pdf_path):
    root_dir = Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\pdf2image")
    os.makedirs(root_dir, exist_ok=True)

    output_dir = root_dir / pdf_path.stem
    os.makedirs(output_dir, exist_ok=True)

    total_pages = int(pdfinfo_from_path(str(pdf_path))["Pages"])

    output_images = []
    for i in range(1, total_pages + 1):
        img_path = output_dir / f"page_{i}.png"

        if not img_path.exists():
            image = convert_from_path(str(pdf_path), dpi=300, first_page=i, last_page=i, fmt="png")[0]
            image.save(img_path, "PNG")

        output_images.append({
            "pdf_path": str(pdf_path),
            "image_path": img_path,
            "page_no": i,
            "total_pages": total_pages
        })

    return output_images

def select_model(pdf_path):
    foreign = ['미얀마',  '몽골', '스리랑카', '우즈베키스탄', '방글라데시', '필리핀', '태국', '파키스탄', '키르키스스탄', '캄보디아', '인도네시아', '우즈베키스탄', '라오스', '동티모르', '네팔', '타지키스탄']
    if any(name in pdf_path.name for name in foreign):
        model = model_foreign
        print(f"적용 모델: {model_foreign}")
    else:
        model = model_basic
    return model

def extract(input_jpg, model):
    basic_prompt = """
    너의 역할은 입력 자료를 검색 및 임베딩용 텍스트로 변환하는거야.
    ocr처럼 있는 그대로 추출하는 것이 목적이므로, 절대 해석, 요약, 번역, 정리, 설명하지마.

    규칙
    1. 원본 자료의 모든 내용(특히 텍스트)을 그대로 추출해
    2. 텍스트는 한국어뿐만 아니라 베트남어, 몽골어, 러시아어 등이 포함될 수 있으며 번역없이 언어 그대로 추출한다.
    3. 자료에 없는 내용을 생성하지마. 추론, 보완 금지
    4. 이미지가 포함되면 해당 이미지에 대한 묘사를 1~2 문장 추가해
    5. 문서의 구조를 그대로 유지해. 레이아웃, 제목, 항목, bullet, 들여쓰기 등 유지해. 계층구조를 유지해.
    6. 좌측 페이지와 우측 페이지가 함께 포함된 양면 펼침면이 있을 수 있어. 읽기 순서를 유지하여 좌측 내용을 모두 추출한 후 우측 내용을 추출하여 내용이 서로 섞이지 않도록 해
    7. 자료에 포함된 내용의 순서를 바꾸지마
    8. 만약 표가 포함되면, 행과 열의 의미를 설명하고, 관계가 드러나도록 작성해. 표가 없다면 생략해
    9. 차트나 도표가 포함되면, 범례, 주요 수치, 추세 등을 설명해. 차트나 도표가 없다면 생략해
    10. 텍스트 인식이 어려운 부분은 [불분명]으로 표시해
    11. "요청하신대로", "추출했습니다" 등의 작업 수행 보고나 안내 문구는 출력하지마
    12. 아무것도 없는 빈페이지인 경우, "빈페이지입니다."로 출력해
    """

    response = client.responses.create(
        model=model,
        input=[
            {
            "role": "user",
            "content": [
                {"type": "input_text", "text": basic_prompt},
                {"type": "input_image", "image_url": image2url(input_jpg), "detail": "auto"}
            ],
        }
        ],
        max_output_tokens = max_output_tokens
    )

    result_text = response.output_text.strip()

    return result_text

def image2url(input_jpg):
    input_jpg = Path(input_jpg)
    mime_type = mimetypes.guess_type(input_jpg.name)[0] or "image/jpeg"
    encoded = base64.b64encode(input_jpg.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


# 페이지별 Markdown 캐시 파일 경로를 만든다.
def make_page_cache_path(cache_dir, page_no):
    return cache_dir / f"page_{page_no:04d}.md"


# 텍스트를 임시 파일에 먼저 저장한 뒤 최종 파일로 교체하여 중단 시 손상을 방지한다.
def save_text_atomic(output_path, text):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = output_path.with_name(output_path.name + ".tmp")
    temp_path.write_text(text.rstrip() + "\n", encoding="utf-8")
    temp_path.replace(output_path)


# 저장된 페이지별 Markdown 결과가 정상 캐시인지 확인한다.
def is_valid_page_cache(cache_path, page_no):
    if not cache_path.exists() or cache_path.stat().st_size == 0:
        return False

    page_text = cache_path.read_text(encoding="utf-8")
    expected_marker = f"<!--페이지 {page_no}-->"

    return page_text.strip().startswith(expected_marker)


# items에 저장된 페이지별 결과를 페이지 순서대로 합쳐 최종 Markdown 파일을 만든다.
def write_markdown(items, md_path):
    ordered_items = sorted(items, key=lambda item: item["page_no"])

    merged_text = "\n\n".join(
        item["page_text"].strip()
        for item in ordered_items
    )

    save_text_atomic(md_path, merged_text)


def extract_pdf(pdf_path, md_path, cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)

    items = []
    output_images = pdftoimage(pdf_path)

    model = select_model(pdf_path)

    for image in output_images:
        input_jpg = image['image_path']
        current_page = image['page_no']

        cache_path = make_page_cache_path(cache_dir, current_page)
        if is_valid_page_cache(cache_path, current_page):
            print(f"cache: {pdf_path.name} {current_page}쪽")
            page_text = cache_path.read_text(encoding="utf-8").strip()
        else:
            print(f"추출 중: {pdf_path.name} {current_page}쪽")
            result_text = extract(input_jpg, model)
            page_text = f"<!--페이지 {current_page}-->\n\n{result_text.strip()}"
            
            save_text_atomic(cache_path, page_text)

        items.append({
            "pdf_path": pdf_path,
            "page_no": current_page,
            "page_text": page_text,
            "total_pages": image['total_pages']
        })
    
    write_markdown(items, md_path)
    print(f"완료: {md_path}")

    return items


def full_extraction():
    path_list = [Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1"), Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF2")]

    pdf1 = sorted([p for p in path_list[0].iterdir()])
    pdf2 = sorted([p for p in path_list[1].iterdir()])

    total = len(pdf1) + len(pdf2)

    jobs = []
    for pdf_path in pdf1 + pdf2:
        md_path = Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\PDF1_text") / f"{pdf_path.stem}.md"
        cache_dir = Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\PDF1_text") / "cache" / pdf_path.stem
        cache_dir.mkdir(parents=True, exist_ok=True)
        jobs.append((pdf_path, md_path, cache_dir))


    done_count = 0
    failed_count = 0

    for i, (pdf_path, md_path, cache_dir) in enumerate(jobs, 1):
        print(f"{i}/{total} - {pdf_path.name}")
        try:
            extract_pdf(pdf_path, md_path, cache_dir)
            done_count += 1
        except KeyboardInterrupt:
            print("stop")
            raise
        except Exception as e:
            failed_count += 1
            print(f"fail {pdf_path.name}: {e}")

    print(f"완료: {done_count}, 실패: {failed_count}")
        
def sample_extraction():
    test_path1 = [Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\[2017-교육미디어-41]외국인 근로자용 안전보건자료 활용가이드_스리랑카.pdf"),
                 Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\[2017-교육미디어-757]개도국(미얀마)포스터5종_국내판(웹용).pdf"),
                 Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\[2017-교육미디어-OPL]방글라데시_서비스.pdf"),
                 Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\[2017-교육미디어-OPL]우즈베키스탄_서비스.pdf"),
                 Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\[2017-교육미디어-OPL]인도네시아_서비스.pdf")]
                 # Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\안전보건공단 미디어개발부 리플렛_최종 도련x.pdf")]
    
    test_path2 = [Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\택배_리플렛.pdf"),
                  Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\근로자환경조사_영문리플렛_05_최종.pdf"),
                  Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF1\\안전검사 신청안내(리플렛).pdf"),
                  Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\RAW\\PDF2\\(260126)중대재해 발생 알림(1)_제조 - 스리랑카어.pdf")]

    total = len(test_path2)
    jobs = []
    for pdf_path in test_path2:
        md_path = Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\extract_output") / f"{pdf_path.stem}.md"
        cache_dir = Path("C:\\Users\\darle\\OneDrive\\문서\\유니스트\\유니스트\\초과학기\\프로젝트랩\\extract_output") / "cache" / pdf_path.stem
        jobs.append((pdf_path, md_path, cache_dir))


    done_count = 0
    failed_count = 0

    for i, (pdf_path, md_path, cache_dir) in enumerate(jobs, 1):
        print(f"{i}/{total} - {pdf_path.name}")
        try:
            extract_pdf(pdf_path, md_path, cache_dir)
            done_count += 1
        except KeyboardInterrupt:
            print("stop")
            raise
        except Exception as e:
            failed_count += 1
            print(f"fail {pdf_path.name}: {e}")

    print(f"완료: {done_count}, 실패: {failed_count}")
    
if __name__ == "__main__":
    full_extraction()
    #sample_extraction()