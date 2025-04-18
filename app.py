# -*- coding: utf-8 -*-
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import google.generativeai as genai
from PIL import Image, UnidentifiedImageError # UnidentifiedImageError 추가
import io
import traceback
from flask_cors import CORS
import re

# .env 파일 로드 (애플리케이션 시작 시)
load_dotenv()

app = Flask(__name__)
# 개발 중에는 모든 출처 허용, 프로덕션에서는 특정 출처 지정 권장
CORS(app)

# --- API 키 설정 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("FATAL ERROR: GEMINI_API_KEY environment variable is not set.")
    # 프로덕션 환경에서는 로깅 후 안전하게 종료
    # exit(1) # 서버 자체를 종료시키는 것은 좋지 않을 수 있음
    # 대신, 요청 처리 시 키가 없으면 에러 반환하는 방식으로 변경 가능
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        print("Google Gemini API configured successfully.")
    except Exception as e:
        print(f"FATAL ERROR: Failed to configure Google Gemini API: {e}")
        # API 구성 실패 시에도 서버 실행은 가능하게 하되, 요청 시 에러 반환
        GEMINI_API_KEY = None # 키를 None으로 설정하여 이후 체크에서 걸리도록 함

# --- Helper Functions ---

def get_band_suggestion(analysis_text):
    """Generate a bandage change recommendation based on the Gemini analysis text."""
    if not analysis_text or "Analysis failed" in analysis_text or "analysis request was blocked" in analysis_text:
        return "Analysis unavailable, cannot provide suggestion."

    suggestions = []
    # 기준 밴드 정보 명시
    base_suggestion = "Bandage (approx. 7.6x7.6cm / 3x3 inch, 3mm thick) based suggestions:"
    suggestions.append(base_suggestion)
    analysis_lower = analysis_text.lower() # 비교를 위해 소문자로 변환

    # 1. 크기 추정 (정규표현식 강화)
    size_found = False
    # 다양한 형식(e.g., 2.5 x 3.1 cm, 2.5x3.1cm, 2x3 cm) 처리
    size_match = re.search(r'approx\.?\s*(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*cm', analysis_lower)
    if size_match:
        try:
            dim1 = float(size_match.group(1))
            dim2 = float(size_match.group(2))
            # 기준 크기 (인치 변환 고려 또는 cm 기준 유지)
            if dim1 > 7.6 or dim2 > 7.6:
                suggestions.append("• *Size:* Wound might be larger than one bandage (7.6x7.6cm). Consider using multiple bandages or a larger size if available.")
                size_found = True
            else:
                suggestions.append("• *Size:* Wound likely fits within one bandage. Ensure the bandage fully covers the wound bed with some margin.")
                size_found = True
        except ValueError:
            print(f"Size number parsing error from regex match: {size_match.groups()}")
    # 정규식 실패 또는 미발견 시 텍스트 기반 추론
    if not size_found:
        if "large size" in analysis_lower or "larger than" in analysis_lower or "extensive area" in analysis_lower:
            suggestions.append("• *Size:* Wound description suggests it might be large. Verify if one bandage (7.6x7.6cm) provides adequate coverage.")
            size_found = True
        elif "difficult to estimate size" in analysis_lower or "size estimation unclear" in analysis_lower:
             suggestions.append("• *Size:* AI could not reliably estimate size. Please visually check if one bandage (7.6x7.6cm) is sufficient.")
             size_found = True # <-- 여기가 72번째 줄일 가능성이 높습니다. 들여쓰기를 확인하세요.

    if not size_found: # 어떤 정보도 없을 경우
        suggestions.append("• *Size:* Wound size information not clear in the analysis. Please verify coverage manually.")



    # 2. 삼출물 양 기반 교체 주기 (키워드 확장)
    exudate_suggestion_added = False
    # 심한 경우 우선 체크
    if "severe exudate" in analysis_lower or "heavy exudate" in analysis_lower or "copious drainage" in analysis_lower or "severe pus" in analysis_lower or "heavy pus" in analysis_lower:
        suggestions.append("• *Replacement (Severe Exudate):* Bandage (3mm thick) may saturate quickly. Change at least twice a day or whenever saturated. **Consult a professional immediately.**")
        exudate_suggestion_added = True
    elif "moderate exudate" in analysis_lower or "moderate drainage" in analysis_lower or "moderate pus" in analysis_lower:
        suggestions.append("• *Replacement (Moderate Exudate):* Recommend changing 1-2 times a day. Monitor bandage saturation.")
        exudate_suggestion_added = True
    elif "mild exudate" in analysis_lower or "scant drainage" in analysis_lower or "mild pus" in analysis_lower:
        suggestions.append("• *Replacement (Mild Exudate):* Change once a day or every other day. Check bandage condition.")
        exudate_suggestion_added = True
    elif "no exudate" in analysis_lower or "wound dry" in analysis_lower or "no drainage" in analysis_lower or "no pus" in analysis_lower:
        suggestions.append("• *Replacement (None/Dry):* Use bandage for protection and moisture balance. Change every 1-3 days as advised by a professional, or if soiled/detached.")
        exudate_suggestion_added = True

    if not exudate_suggestion_added:
        suggestions.append("• *Replacement Frequency:* Exudate level unclear. Change bandage immediately if wet, soiled, or detached. Follow professional guidance.")

    # 3. 감염 징후 및 기타 고려사항
    infection_warning = False
    # 감염 의심 키워드 확장
    if ("infection sign" in analysis_lower or "heavy pus" in analysis_lower or
        "foul odor suspected" in analysis_lower or # 프롬프트에서 시각적 징후만 요청하므로 'suspected' 추가
        "severe redness spreading" in analysis_lower or "significant edema" in analysis_lower or
        "cellulitis suspected" in analysis_lower or "increasing pain reported" in analysis_lower): # 통증은 이미지로 알 수 없지만, 만약 언급된다면
        suggestions.append("\n**⚠️ URGENT WARNING:** Analysis suggests potential signs of infection! **Seek immediate medical attention from a healthcare professional!** Do not rely solely on this analysis.")
        infection_warning = True

    if "necrotic tissue" in analysis_lower or "black tissue" in analysis_lower or "eschar" in analysis_lower or "gangrene" in analysis_lower:
        suggestions.append("\n• *Note:* Presence of necrotic tissue (black/brown/yellow slough) can impede healing. Professional assessment for potential debridement (removal) is crucial.")

    # 감염 경고가 없을 때 일반 관리 조언 추가
    if not infection_warning:
        suggestions.append("\n• *General Care:* Keep the wound and surrounding skin clean and dry (unless specific moisture therapy advised). Proper blood sugar control and nutrition are vital for diabetic wound healing.")

    return "\n".join(suggestions)


def estimate_wagner_grade(analysis_text):
    """Gemini 분석 텍스트(시각적 설명)를 기반으로 Wagner Grade 추정"""
    if not analysis_text or "Analysis failed" in analysis_text or "analysis request was blocked" in analysis_text:
        return "Analysis unavailable, cannot estimate stage."

    analysis_lower = analysis_text.lower()
    possible_grade = "Grade Unknown / Insufficient Info"  # Initialize with default value
    
    # 면책 조항은 항상 포함
    caveat = ("\n\n**Disclaimer:** This is an AI's interpretation based *solely* on the visual description provided by another AI analysis of the image. It is **NOT** a medical diagnosis or official Wagner Grade. Accurate staging requires clinical examination by a qualified healthcare professional.")

    # Try to extract Wagner Grade directly from analysis text first
    wagner_match = re.search(r'grade\s*(\d)\s*:', analysis_lower)
    if wagner_match:
        grade_num = wagner_match.group(1)
        possible_grade = f"Grade {grade_num}"
        
        # Map grade numbers to descriptions
        grade_descriptions = {
            '0': "No ulcer, intact skin",
            '1': "Superficial ulcer (epidermis/dermis only)",
            '2': "Deep ulcer (to tendon, joint capsule)",
            '3': "Deep ulcer with abscess/osteomyelitis",
            '4': "Localized gangrene (toe, forefoot)",
            '5': "Extensive gangrene (whole foot)"
        }
        
        if grade_num in grade_descriptions:
            possible_grade += f": {grade_descriptions[grade_num]}"
        return f"{possible_grade}{caveat}"

    # If no direct grade found, proceed with keyword analysis
    # 가장 심각한 등급부터 확인 (키워드 기반)
    # Grade 5: 발 전체 괴사
    if "grade 5" in analysis_lower or "extensive gangrene involving the whole foot" in analysis_lower or "gangrene of the entire foot" in analysis_lower:
        possible_grade = "Grade 5: Extensive gangrene (whole foot)"
    
    # Grade 4: 국소적 괴사 (발가락, 발 뒤꿈치 등)
    elif "grade 4" in analysis_lower or "localized gangrene" in analysis_lower or "gangrene present on" in analysis_lower:
        possible_grade = "Grade 4: Localized gangrene (toe, forefoot)"
    
    # Grade 3: 깊은 감염 (농양, 골수염) 또는 심부 조직 노출 + 감염 징후
    elif "grade 3" in analysis_lower or "osteomyelitis" in analysis_lower or "deep infection" in analysis_lower or "abscess" in analysis_lower:
        possible_grade = "Grade 3: Deep ulcer with abscess/osteomyelitis"
    
    # Grade 2: 깊은 궤양 (힘줄, 관절낭, 뼈 노출 - 감염 징후 '없이')
    elif "grade 2" in analysis_lower or "tendon exposed" in analysis_lower or "joint capsule exposed" in analysis_lower or "bone exposed" in analysis_lower:
        possible_grade = "Grade 2: Deep ulcer (to tendon, joint capsule)"
    
    # Grade 1: 표재성 궤양 (진피까지만 침범)
    elif "grade 1" in analysis_lower or "superficial ulcer" in analysis_lower or "skin layer only" in analysis_lower:
        possible_grade = "Grade 1: Superficial ulcer (epidermis/dermis only)"
    
    # Grade 0: 궤양 없음, 피부 온전
    elif "grade 0" in analysis_lower or "no ulcer" in analysis_lower or "intact skin" in analysis_lower:
        possible_grade = "Grade 0: No ulcer, intact skin"
    
    # If still no grade found but analysis exists
    elif "ulcer" in analysis_lower or "wound" in analysis_lower:
        possible_grade = "Grade Unknown: Wound present but insufficient information for precise grading"
    
    # Final fallback
    else:
        possible_grade = "Grade Unknown: No wound characteristics detected"

    return f"{possible_grade}{caveat}"


def get_necrosis_visual_stage(analysis_text):
    """Gemini 분석 텍스트를 기반으로 괴사/조직 상태 시각화 키 반환"""
    if not analysis_text or "Analysis failed" in analysis_text or "analysis request was blocked" in analysis_text:
        return "unknown" # 분석 실패 시 unknown 반환

    analysis_lower = analysis_text.lower()
    # 가장 심각한 상태부터 확인
    if "gangrene" in analysis_lower: return "gangrene"
    if "eschar" in analysis_lower or "black tissue" in analysis_lower or "necrotic" in analysis_lower : return "eschar" # necrotic 포함
    if "slough" in analysis_lower or "yellow tissue" in analysis_lower or "tan tissue" in analysis_lower or "white tissue" in analysis_lower: # slough 색상 다양
        # 만약 eschar/gangrene도 같이 언급되면 더 심각한 상태 우선 (위에서 이미 걸러짐)
        return "slough"
    if "granulation tissue" in analysis_lower or "red tissue" in analysis_lower or "pink tissue" in analysis_lower or "healthy tissue base" in analysis_lower:
        # 심각한 조직(괴사, 부육) 언급 없이 건강한 조직만 언급될 때
        if not ("gangrene" in analysis_lower or "eschar" in analysis_lower or "black tissue" in analysis_lower or "slough" in analysis_lower or "necrotic" in analysis_lower):
            return "healthy_granulation"
    if "no ulcer" in analysis_lower or "skin intact" in analysis_lower or "healed" in analysis_lower:
        # 다른 조직 언급 없이 피부 온전 또는 치유 언급 시
        if not ("gangrene" in analysis_lower or "eschar" in analysis_lower or "slough" in analysis_lower or "granulation" in analysis_lower):
            return "no_ulcer"

    # 위의 어떤 조건에도 해당하지 않으면 unknown 반환
    return "unknown"


# --- Flask Route ---
@app.route('/analyze', methods=['POST']) # methods 수정
def analyze_image_route():
    # API 키 재확인 (서버 시작 시 실패했을 경우 대비)
    if not GEMINI_API_KEY:
        print("Error: Gemini API key is not configured.")
        return jsonify({"error": "Server configuration error: API key missing."}), 500

    if 'image' not in request.files:
        return jsonify({"error": "No 'image' file part in the request."}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No file selected."}), 400

    # 허용 확장자 (소문자)
    allowed_extensions = {'png', 'jpg', 'jpeg', 'webp'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if file_ext not in allowed_extensions:
        return jsonify({"error": f"Invalid File Type: '{file_ext}'. Allowed types: {', '.join(allowed_extensions)}"}), 400

    try:
        # 메모리에서 이미지 열기 (파일 저장 불필요)
        img_bytes = file.read() # 바이트로 읽기
        try:
            img = Image.open(io.BytesIO(img_bytes))
            # 이미지 기본 정보 로깅 (디버깅용)
            print(f"Image opened: format={img.format}, size={img.size}, mode={img.mode}")
        except UnidentifiedImageError:
            print(f"Error: Cannot identify image file. Filename: {file.filename}")
            return jsonify({"error": "Invalid or corrupted image file."}), 400
        except Exception as img_err: # 기타 이미지 처리 오류
            print(f"Error opening image: {img_err}")
            traceback.print_exc()
            return jsonify({"error": "Could not process the uploaded image."}), 500


        # 모델 선택 (최신 안정 버전 권장)
        # gemini-1.5-flash는 빠르고 비용 효율적, gemini-1.5-pro는 더 높은 성능
        model = genai.GenerativeModel('gemini-1.5-flash')

        # --- 프롬프트 개선 (더 명확하고 구조화, 영어로 통일) ---
        # Wagner Grade 직접 판단 요청 제거, 시각적 특징 상세 묘사 요청 강화
        prompt = """
Analyze the provided image of a foot with a wound, likely a diabetic foot ulcer. Provide a detailed, objective visual description in English, focusing *only* on what is visible in the image. Structure the analysis clearly and always assign a Wagner Grade (0-5) even if the image quality is poor. Follow this exact structure:

1. **Wound Bed Tissue Description (REQUIRED):**
   - Identify ALL visible tissue types (Granulation, Slough, Eschar, Necrotic, Healthy Epithelium).
   - Estimate percentage coverage for each (e.g., "60% Granulation, 30% Slough, 10% Eschar").
   - Describe color/appearance of each tissue (e.g., "red/pink granulation", "yellow slough", "black dry eschar").

2. **Wound Dimensions (REQUIRED):**
   - Estimate size (length x width) in cm (e.g., "3.5 x 2.0 cm").
   - If unclear: "Size estimation difficult" but still attempt approximate range.

3. **Exudate Assessment (REQUIRED):**
   - Visible amount: "None", "Mild", "Moderate", "Severe".
   - Type if visible: "Serous", "Sanguineous", "Purulent".
   - If unclear: "Exudate not clearly visible".

4. **Periwound Skin (REQUIRED):**
   - Condition: "Intact", "Erythema", "Edema", "Maceration", "Callus", etc.
   - Extent of abnormalities (e.g., "Erythema extends 2 cm around wound").

5. **Wound Edges (REQUIRED):**
   - Description: "Well-defined", "Irregular", "Undermined", "Rolled".
   - If unclear: "Edge characteristics not clearly visible".

6. **Depth & Structures (REQUIRED):**
   - Depth: "Superficial", "Partial-thickness", "Full-thickness", "Deep".
   - Visible structures: Explicitly state if "Tendon", "Bone", "Joint" are visible.
   - If unclear: "Depth assessment limited by image quality".

7. **Infection Signs (REQUIRED):**
   - Visual signs: "Erythema", "Purulent exudate", "Edema", etc.
   - Explicit disclaimer: "Clinical assessment required for infection confirmation"

**Final Notes:**
- If image quality is poor, still attempt ALL assessments marking uncertain items.
- NEVER omit Wagner Grade - always provide best estimate.
- Use "Unclear" only when absolutely no visual evidence exists for a parameter.
- Maintain objective tone, avoiding diagnostic language.
- Make sure to crop image to parts that contains the wound

**Output Format:** Strictly follow the numbered structure above for every analysis. For Wagner Grade, include both the number and description (e.g., "Grade 2: Deep ulcer reaching tendon"). 
"""
        

        # --- 안전 설정 (필요 시 조정) ---
        # safety_settings = [
        #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        # ]
        # response = model.generate_content([prompt, img], safety_settings=safety_settings)

        # --- 기본 안전 설정으로 실행 ---
        response = model.generate_content([prompt, img])

        # --- 응답 처리 강화 ---
        analysis_text = ""
        try:
            # response.text 접근 시도
            analysis_text = response.text
            print("--- Gemini Analysis Result ---")
            print(analysis_text)
            print("-----------------------------")
        except ValueError as ve:
            # response.prompt_feedback 확인 (콘텐츠 차단 시)
            print(f"Warning: Could not access response.text directly. ValueError: {ve}")
            try:
                feedback = response.prompt_feedback
                if feedback.block_reason:
                    error_message = f"AI analysis was blocked. Reason: {feedback.block_reason}. "
                    if feedback.block_reason_message:
                        error_message += f"Details: {feedback.block_reason_message}"
                    print(f"Gemini API Blocked: {error_message}")
                    analysis_text = error_message # 차단 메시지를 분석 결과로 사용
                else:
                    # 차단되지 않았는데 text 접근 불가 시 (드문 경우)
                    analysis_text = "AI analysis result is empty or in unexpected format. Please try again."
                    print("Gemini API response is empty or not text, but not blocked.")
            except Exception as fb_err:
                print(f"Error accessing prompt_feedback: {fb_err}")
                analysis_text = "Error retrieving AI analysis result and feedback."
        except Exception as resp_err: # 기타 response 관련 예외
            print(f"Unexpected error processing Gemini response: {resp_err}")
            traceback.print_exc()
            analysis_text = "Unexpected error processing AI response."


        # 분석 텍스트 기반으로 추가 정보 생성
        suggestion_text = get_band_suggestion(analysis_text)
        possible_wagner = estimate_wagner_grade(analysis_text)
        necrosis_stage_key = get_necrosis_visual_stage(analysis_text)

        return jsonify({
            "analysis": analysis_text,
            "suggestion": suggestion_text,
            "possible_wagner_grade": possible_wagner,
            "necrosis_stage": necrosis_stage_key # HTML/JS에서 사용할 키
        })

    # --- 구체적인 Gemini API 예외 처리 ---
    except genai.types.BlockedPromptException as bpe:
        print(f"ERROR - Gemini API BlockedPromptException: {bpe}")
        return jsonify({"error": "AI analysis request was blocked due to safety settings or invalid prompt."}), 400 # 400 Bad Request가 더 적절할 수 있음
    except genai.types.StopCandidateException as sce:
        print(f"ERROR - Gemini API StopCandidateException: {sce}")
        return jsonify({"error": "AI analysis result generation was stopped prematurely."}), 500
    except Exception as e: # 포괄적인 서버 오류 처리
        print(f"ERROR - Internal Server Error: {e}")
        traceback.print_exc() # 서버 로그에 상세 스택 트레이스 출력
        return jsonify({"error": "An internal server error occurred during analysis. Please try again later."}), 500

if __name__ == '__main__':
    # 개발 시 debug=True 사용, 프로덕션에서는 False로 변경
    # host='0.0.0.0' 로 설정하면 외부에서도 접근 가능 (방화벽 설정 필요)
    print("Starting Flask server...")
    app.run(debug=True, host='0.0.0.0', port=5500)
