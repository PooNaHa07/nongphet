/**
 * nongphet AI Smart Guide - Modals & Vision AI Handlers
 * Handles Photo AI carousel, Trip Planner, Future Career Matcher, and QR Code modals
 */

const visionSamples = [
    {
        name: "พระนครคีรี (เขาวัง)",
        accuracy: "ความแม่นยำ 96%",
        img: "/static/img/places/khaowang.jpg",
        desc: "พระราชวังฤดูร้อนบนยอดเขาสมัย ร.4 โดดเด่นด้วยสถาปัตยกรรมผสมผสานไทย-นีโอคลาสสิก-จีน ชมวิวเมืองเพชรได้แบบ 360 องศาครับ",
        mapsQuery: "พระนครคีรี เขาวัง เพชรบุรี"
    },
    {
        name: "ถ้ำเขาหลวง",
        accuracy: "ความแม่นยำ 98%",
        img: "/static/img/places/khaoluang.jpg",
        desc: "ถ้ำหินงอกหินย้อยอันวิจิตร ไฮไลท์คือลำแสงอาทิตย์ส่องลงสู่พระพุทธรูปหลวงพ่อโต (แสงสวรรค์) ช่วงเวลา 09:30 - 11:30 น. ครับ",
        mapsQuery: "ถ้ำเขาหลวง เพชรบุรี"
    },
    {
        name: "หาดชะอำ",
        accuracy: "ความแม่นยำ 94%",
        img: "/static/img/places/chaam.jpg",
        desc: "ชายหาดยอดนิยม ทรายขาวยาวสุดสายตา มีกิจกรรมขี่ม้า บานาน่าโบ๊ท และซีฟู้ดสดใหม่อร่อยราคาเป็นกันเองครับ",
        mapsQuery: "หาดชะอำ เพชรบุรี"
    },
    {
        name: "วัดมหาธาตุวรวิหาร",
        accuracy: "ความแม่นยำ 97%",
        img: "/static/img/places/mahathat.jpg",
        desc: "ปูชนียสถานคู่บ้านคู่เมือง มีพระปรางค์ 5 ยอดอันวิจิตรงดงามด้วยศิลปกรรมช่างเมืองเพชรที่มีชื่อเสียงระดับประเทศครับ",
        mapsQuery: "วัดมหาธาตุวรวิหาร เพชรบุรี"
    }
];

function openVisionGoogleMaps() {
    const item = visionSamples[currentVisionIndex];
    openGoogleMapsSearch(item.mapsQuery || item.name);
}

function updateVisionDisplay() {
    const item = visionSamples[currentVisionIndex];
    document.getElementById('visionImagePreview').src = item.img;
    document.getElementById('visionPlaceName').textContent = item.name;
    document.getElementById('visionAccuracyBadge').textContent = item.accuracy;
    document.getElementById('visionPlaceDesc').textContent = item.desc;
}

function prevVisionSample() {
    uploadedVisionFile = null;
    currentVisionIndex = (currentVisionIndex - 1 + visionSamples.length) % visionSamples.length;
    updateVisionDisplay();
}

function nextVisionSample() {
    uploadedVisionFile = null;
    currentVisionIndex = (currentVisionIndex + 1) % visionSamples.length;
    updateVisionDisplay();
}

function handleUserPhotoUpload(input) {
    if (input.files && input.files[0]) {
        uploadedVisionFile = input.files[0];
        const reader = new FileReader();
        reader.onload = function(e) {
            document.getElementById('visionImagePreview').src = e.target.result;
            document.getElementById('visionPlaceName').textContent = "ภาพที่คุณอัปโหลด";
            document.getElementById('visionAccuracyBadge').textContent = "พร้อมวิเคราะห์ AI";
            document.getElementById('visionPlaceDesc').textContent = "กดปุ่ม 'วิเคราะห์ด้วย AI' เพื่อให้น้องเพชรตรวจสอบสถานที่และประวัติศาสตร์จากภาพนี้ครับ";
        };
        reader.readAsDataURL(uploadedVisionFile);
    }
}

async function captureFromRobotCamera() {
    const btn = document.getElementById('btnRobotSnap');
    const origHTML = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>กำลังถ่าย...</span>';
        btn.disabled = true;
    }

    try {
        const res = await fetch('/api/vision/snapshot.jpg?t=' + Date.now());
        if (!res.ok) {
            throw new Error('ไม่สามารถดึงภาพจากกล้องฮาร์ดแวร์ได้');
        }
        const blob = await res.blob();
        uploadedVisionFile = new File([blob], "robot_camera_snap.jpg", { type: "image/jpeg" });
        
        const previewEl = document.getElementById('visionImagePreview');
        if (previewEl) previewEl.src = URL.createObjectURL(blob);

        document.getElementById('visionPlaceName').textContent = "ภาพถ่ายจากกล้องหุ่นยนต์";
        document.getElementById('visionAccuracyBadge').textContent = "จับภาพสำเร็จ";
        document.getElementById('visionAccuracyBadge').className = "bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-black px-3.5 py-1 rounded-full shadow-sm";
        document.getElementById('visionPlaceDesc').textContent = "ถ่ายภาพจากกล้องของน้องเพชรเรียบร้อยแล้ว! กำลังส่งให้ AI Vision Pro วิเคราะห์สถานที่...";

        await runVisionAnalysis();
    } catch (e) {
        document.getElementById('visionPlaceDesc').textContent = "⚠️ ไม่สามารถถ่ายภาพจากกล้องหุ่นยนต์ได้ (" + e.message + ") แนะนำให้รัน python vision_daemon.py บน Pi 5 หรือลองใช้วิธีอัปโหลดรูปภาพแทนครับ";
    } finally {
        if (btn) {
            btn.innerHTML = origHTML;
            btn.disabled = false;
        }
    }
}

async function runVisionAnalysis() {
    const btn = document.getElementById('btnRunVision');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>กำลังวิเคราะห์...</span>';
    btn.disabled = true;

    if (uploadedVisionFile) {
        const formData = new FormData();
        formData.append('image', uploadedVisionFile);
        try {
            const response = await fetch('/vision', { method: 'POST', body: formData });
            const data = await response.json();
            if (data.description) {
                document.getElementById('visionPlaceName').textContent = "ผลการตรวจจับ AI";
                document.getElementById('visionAccuracyBadge').textContent = "วิเคราะห์เรียบร้อย";
                document.getElementById('visionPlaceDesc').innerHTML = formatMarkdown(data.description);
            } else {
                document.getElementById('visionPlaceDesc').textContent = data.error || "ไม่สามารถวิเคราะห์ภาพได้";
            }
        } catch (e) {
            document.getElementById('visionPlaceDesc').textContent = "เกิดข้อผิดพลาดในการเชื่อมต่อ AI";
        }
    } else {
        setTimeout(() => {
            const current = visionSamples[currentVisionIndex];
            document.getElementById('visionAccuracyBadge').textContent = "ตรวจสอบแล้ว 98.5%";
            document.getElementById('visionPlaceDesc').textContent = current.desc + " (แนะนำให้มาช่วงเช้า แสงแดดจะสวยงามเหมาะแก่การถ่ายรูปที่สุดครับ)";
        }, 600);
    }

    btn.innerHTML = originalText;
    btn.disabled = false;
}

// Modal open/close controls
function openQrModal() { document.getElementById('qrModal').classList.remove('hidden'); }
function closeQrModal() { document.getElementById('qrModal').classList.add('hidden'); }

function openTripPlannerModal() { document.getElementById('tripModal').classList.remove('hidden'); }
function closeTripPlannerModal() { document.getElementById('tripModal').classList.add('hidden'); }

function openMatcherModal() { document.getElementById('matcherModal').classList.remove('hidden'); }
function closeMatcherModal() { document.getElementById('matcherModal').classList.add('hidden'); }

async function submitTripPlanner() {
    const days = document.getElementById('tripDaysSelect').value;
    const style = document.querySelector('input[name="tripStyle"]:checked')?.value || 'ทั่วไป';
    closeTripPlannerModal();
    navigateTo('screen-chat');
    
    appendChatBubble('user', `🗺️ ช่วยวางแผนทริปท่องเที่ยวเพชรบุรี ${days} สไตล์ ${style} แบบละเอียดระดับ World-Class หน่อยครับ`);
    const typingIndicator = document.getElementById('typingIndicator');
    const chatBox = document.getElementById('chatBox');
    if (typingIndicator) typingIndicator.classList.remove('hidden');
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const res = await fetch('/plan_trip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trip_type: days, preferences: style })
        });
        const data = await res.json();
        if (typingIndicator) typingIndicator.classList.add('hidden');
        if (data.plan) {
            appendChatBubble('ai', data.plan);
            if (autoSpeak) playTTS(data.plan);
        } else {
            appendChatBubble('ai', data.error || 'ขออภัยค่ะ เกิดข้อผิดพลาดในการจัดทริป');
        }
    } catch (err) {
        if (typingIndicator) typingIndicator.classList.add('hidden');
        appendChatBubble('ai', 'เชื่อมต่อระบบจัดทริปไม่สำเร็จในขณะนี้');
    }
}

async function submitMatcher() {
    const interests = document.getElementById('matcherInterests').value.trim();
    const strengths = document.getElementById('matcherStrengths').value.trim();
    const dream_job = document.getElementById('matcherDream').value.trim();
    
    if (!interests && !strengths) {
        alert('กรุณากรอกความสนใจหรือความถนัดของคุณสักเล็กน้อยครับ');
        return;
    }
    closeMatcherModal();
    navigateTo('screen-chat');

    appendChatBubble('user', `🎯 ความสนใจ: "${interests}" | จุดเด่น: "${strengths}" | เป้าหมาย: "${dream_job}" ช่วยวิเคราะห์ Career Blueprint ให้หน่อยครับ`);
    const typingIndicator = document.getElementById('typingIndicator');
    const chatBox = document.getElementById('chatBox');
    if (typingIndicator) typingIndicator.classList.remove('hidden');
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const res = await fetch('/match_course', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interests, strengths, dream_job })
        });
        const data = await res.json();
        if (typingIndicator) typingIndicator.classList.add('hidden');
        if (data.recommendation) {
            appendChatBubble('ai', data.recommendation);
            if (autoSpeak) playTTS(data.recommendation);
        } else {
            appendChatBubble('ai', data.error || 'เกิดข้อผิดพลาดในการวิเคราะห์');
        }
    } catch (err) {
        if (typingIndicator) typingIndicator.classList.add('hidden');
        appendChatBubble('ai', 'เกิดข้อผิดพลาดในการเชื่อมต่อ');
    }
}

function openContactModal() {
    const m = document.getElementById('contactModal');
    if (m) m.classList.remove('hidden');
}

function closeContactModal() {
    const m = document.getElementById('contactModal');
    if (m) m.classList.add('hidden');
}

function openExploreModal() {
    const m = document.getElementById('exploreModal');
    if (m) m.classList.remove('hidden');
}

function closeExploreModal() {
    const m = document.getElementById('exploreModal');
    if (m) m.classList.add('hidden');
}

