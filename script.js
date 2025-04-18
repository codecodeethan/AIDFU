document.addEventListener('DOMContentLoaded', () => {
    // ID 참조 수정
    const woundImageInput = document.getElementById('woundImage');
    const fileNameSpan = document.getElementById('fileName');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const imagePreview = document.getElementById('imagePreview'); // ID 수정됨
    const previewPlaceholder = document.getElementById('previewPlaceholder');
    const loadingIndicator = document.getElementById('loadingIndicator'); // ID 수정됨
    const resultsSection = document.getElementById('resultsSection');
    const analysisResultP = document.getElementById('analysisResult');
    const bandSuggestionP = document.getElementById('bandSuggestion');
    const wagnerGradeResultP = document.getElementById('wagnerGradeResult'); // 추가됨
    const necrosisStageTextElement = document.getElementById('necrosisStageText');
    const scaleSegments = document.querySelectorAll('.scale-segment');

    let selectedFile = null;

    woundImageInput.addEventListener('change', (event) => {
        selectedFile = event.target.files[0];
        if (selectedFile) {
            // 파일 유효성 검사 (간단한 이미지 타입 체크)
            if (!selectedFile.type.startsWith('image/')) {
                alert('Please select an image file (e.g., JPG, PNG, WEBP).');
                fileNameSpan.textContent = 'Invalid file type';
                analyzeBtn.disabled = true;
                imagePreview.style.display = 'none';
                previewPlaceholder.style.display = 'block';
                selectedFile = null;
                resultsSection.style.display = 'none'; // 이전 결과 숨기기
                return; // 함수 종료
            }

            fileNameSpan.textContent = selectedFile.name;
            analyzeBtn.disabled = false; // 유효한 파일 선택 시 버튼 활성화

            const reader = new FileReader();
            reader.onload = function(e) {
                imagePreview.src = e.target.result;
                imagePreview.style.display = 'block';
                previewPlaceholder.style.display = 'none';
            }
            reader.readAsDataURL(selectedFile);

            // 새 파일 선택 시 이전 결과 초기화
            resultsSection.style.display = 'none';
            analysisResultP.textContent = '-';
            bandSuggestionP.textContent = '-';
            wagnerGradeResultP.textContent = '-'; // Wagner 결과 초기화
            necrosisStageTextElement.textContent = '';
            scaleSegments.forEach(segment => {
                segment.classList.remove('active');
            });

        } else {
            fileNameSpan.textContent = 'No file selected';
            analyzeBtn.disabled = true;
            imagePreview.style.display = 'none';
            previewPlaceholder.style.display = 'block';
            selectedFile = null;
            resultsSection.style.display = 'none'; // 결과 숨기기
        }
    });

    analyzeBtn.addEventListener('click', async () => {
        if (!selectedFile) {
            alert('Please select an image first.');
            return;
        }

        loadingIndicator.style.display = 'block';
        resultsSection.style.display = 'none';
        analyzeBtn.disabled = true; // 분석 중 버튼 비활성화

        const formData = new FormData();
        formData.append('image', selectedFile);

        try {
            // 백엔드 주소 확인 필요
            const response = await fetch('http://127.0.0.1:5500/analyze', {
                method: 'POST',
                body: formData,
            });

            // 응답 상태 코드 상세 확인
            if (!response.ok) {
                let errorMsg = `Server error: ${response.status} ${response.statusText}`;
                try {
                    // 서버에서 보낸 JSON 에러 메시지 파싱 시도
                    const errorData = await response.json();
                    errorMsg = errorData.error || errorMsg; // 서버 에러 메시지가 있으면 사용
                } catch (e) {
                    // JSON 파싱 실패 시 기본 에러 메시지 유지
                    console.error('Could not parse error response JSON:', e);
                }
                throw new Error(errorMsg); // 에러 발생시켜 catch 블록으로 이동
            }

            const data = await response.json();

            // 결과 표시
            analysisResultP.textContent = data.analysis || "Could not retrieve analysis summary.";
            bandSuggestionP.textContent = data.suggestion || "Could not retrieve bandage recommendation.";
            wagnerGradeResultP.textContent = data.possible_wagner_grade || "Could not retrieve DFU stage information."; // Wagner 결과 표시

            // 괴사 단계 시각화 업데이트
            const necrosisStageKey = data.necrosis_stage || "unknown"; // 기본값 'unknown'
            updateNecrosisScale(necrosisStageKey);

            resultsSection.style.display = 'block'; // 결과 섹션 표시

        } catch (error) {
            console.error('Error during analysis:', error);
            // 사용자에게 에러 메시지 표시 (더 친절하게)
            analysisResultP.textContent = `Analysis failed: ${error.message}`;
            bandSuggestionP.textContent = '-';
            wagnerGradeResultP.textContent = '-';
            necrosisStageTextElement.textContent = 'Could not determine stage due to error.';
            scaleSegments.forEach(segment => segment.classList.remove('active'));
            // 에러 발생 시에도 결과 섹션의 에러 메시지를 보여주기 위해 display='block' 유지 가능
             resultsSection.style.display = 'block'; // 에러 메시지 표시

        } finally {
            // 로딩 인디케이터 숨기기 및 버튼 다시 활성화
            loadingIndicator.style.display = 'none';
            // 파일이 여전히 선택된 상태이면 버튼 활성화
            if (selectedFile) {
                analyzeBtn.disabled = false;
            }
        }
    });

    function updateNecrosisScale(stageKey) {
        // 모든 세그먼트 비활성화
        scaleSegments.forEach(segment => {
            segment.classList.remove('active');
        });

        // 전달받은 stageKey에 해당하는 세그먼트 찾기
        const activeSegment = document.querySelector(`.scale-segment[data-stage="${stageKey}"]`);
        let stageDescription = "Status Classification Pending..."; // 기본 텍스트

        if (activeSegment) {
            activeSegment.classList.add('active'); // 해당 세그먼트 활성화
            // title 속성에서 설명 가져오기 (없으면 stageKey 사용)
            stageDescription = activeSegment.getAttribute('title') || stageKey;
        } else {
            // 해당하는 세그먼트가 없으면 'unknown' 세그먼트 활성화 시도
            const unknownSegment = document.querySelector('.scale-segment[data-stage="unknown"]');
            if (unknownSegment) {
                unknownSegment.classList.add('active');
            }
            stageDescription = "Could not classify status"; // 분류 불가 텍스트
        }

        // 화면에 텍스트 업데이트
        necrosisStageTextElement.textContent = `AI Assessed Status: ${stageDescription}`;
    }
});
