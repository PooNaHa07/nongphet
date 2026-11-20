# -*- coding: utf-8 -*-
"""
routes/knowledge.py — Dynamic Knowledge Base (RAG Retrainable) REST API & Admin Page
"""
import logging
from flask import Blueprint, request, jsonify, render_template

from services.knowledge_manager import kb_manager
from services.text_utils import spoken_text_of


def _bake_answer_voice(answer):
    """อัดเสียงบทพูดที่เพิ่ม/แก้ใหม่ทันที (เรียนรู้ซ้ำแล้วพูดได้เลย) ถ้าอัดไม่ได้ หุ่นจะพูดประโยคกลางแทน"""
    if not answer:
        return False
    from flask import current_app
    if current_app.testing:
        return False  # ระหว่างรันเทสต์ ไม่ต้องสร้างเสียงจริง
    try:
        from services.tts_service import bake_text_in_background
        return bake_text_in_background(answer) is not None
    except Exception as e:
        logger.warning(f"Voice bake skipped: {e}")
        return False
from semantic_retriever import get_semantic_retriever

logger = logging.getLogger("nongphet.knowledge_route")

knowledge_bp = Blueprint('knowledge', __name__)

@knowledge_bp.route('/admin/knowledge')
def knowledge_admin_page():
    """หน้าเว็บจัดการฐานความรู้ (Knowledge Base & RAG Mission Control)"""
    return render_template('knowledge_admin.html')

@knowledge_bp.route('/api/kb/stats', methods=['GET'])
def get_kb_stats():
    """ดึงข้อมูลสถิติของคลังความรู้"""
    return jsonify({
        'status': 'success',
        'stats': kb_manager.get_stats()
    })

@knowledge_bp.route('/api/kb/entries', methods=['GET'])
def get_kb_entries():
    """ดึงรายการหัวข้อความรู้ทั้งหมด รองรับการค้นหา (q) และกรองหมวดหมู่ (intent)"""
    search_q = request.args.get('q', '').strip()
    intent = request.args.get('intent', '').strip()
    entries = kb_manager.list_entries(search=search_q, intent=intent)
    return jsonify({
        'status': 'success',
        'total': len(entries),
        'entries': entries
    })

@knowledge_bp.route('/api/kb/entry/<entry_id>', methods=['GET'])
def get_kb_entry(entry_id):
    """ดึงข้อมูลหัวข้อความรู้ตามรหัส ID"""
    entry = kb_manager.get_entry(entry_id)
    if not entry:
        return jsonify({'status': 'error', 'message': f'ไม่พบหัวข้อความรู้รหัส {entry_id}'}), 404
    return jsonify({
        'status': 'success',
        'entry': entry
    })

@knowledge_bp.route('/api/kb/entry', methods=['POST'])
def create_kb_entry():
    """เพิ่มหัวข้อความรู้ใหม่ พร้อมสั่ง Re-index อัตโนมัติ (AI เรียนรู้ทันที)"""
    data = request.json or {}
    if not data.get('title'):
        return jsonify({'status': 'error', 'message': 'กรุณาระบุชื่อหัวข้อ (title)'}), 400
    if not data.get('answer'):
        return jsonify({'status': 'error', 'message': 'กรุณาระบุเนื้อหาคำตอบ (answer)'}), 400

    try:
        res = kb_manager.add_entry(data, auto_reindex=True)
        res['voice_baking'] = _bake_answer_voice(spoken_text_of(res.get('entry')))
        return jsonify(res), 201
    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 400
    except Exception as e:
        logger.error(f"Error creating KB entry: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@knowledge_bp.route('/api/kb/entry/<entry_id>', methods=['PUT'])
def update_kb_entry(entry_id):
    """แก้ไขหัวข้อความรู้ พร้อมสั่ง Re-index อัตโนมัติ"""
    data = request.json or {}
    try:
        res = kb_manager.update_entry(entry_id, data, auto_reindex=True)
        if 'answer' in data or 'speech' in data:
            res['voice_baking'] = _bake_answer_voice(spoken_text_of(res.get('entry')))
        return jsonify(res), 200
    except KeyError as ke:
        return jsonify({'status': 'error', 'message': str(ke)}), 404
    except Exception as e:
        logger.error(f"Error updating KB entry: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@knowledge_bp.route('/api/kb/entry/<entry_id>', methods=['DELETE'])
def delete_kb_entry(entry_id):
    """ลบหัวข้อความรู้ พร้อมสั่ง Re-index อัตโนมัติ"""
    try:
        res = kb_manager.delete_entry(entry_id, auto_reindex=True)
        return jsonify(res), 200
    except KeyError as ke:
        return jsonify({'status': 'error', 'message': str(ke)}), 404
    except Exception as e:
        logger.error(f"Error deleting KB entry: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@knowledge_bp.route('/api/kb/reindex', methods=['POST'])
def trigger_reindex():
    """สั่ง Re-train / Re-index เวกเตอร์ความรู้ใหม่ทั้งระบบแบบ Hot-Reload"""
    try:
        stats = kb_manager.reindex()
        return jsonify({
            'status': 'success',
            'message': 'AI ทำการคำนวณเวกเตอร์และจดจำความรู้ใหม่เรียบร้อยแล้ว!',
            'stats': stats
        }), 200
    except Exception as e:
        logger.error(f"Reindex error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@knowledge_bp.route('/api/kb/test_query', methods=['POST'])
def test_kb_query():
    """
    ทดสอบจำลองคำถามสดสำหรับกรรมการและผู้พัฒนา
    คำนวณ Cosine Similarity และทดสอบตอบกลับแบบ Real-time
    """
    data = request.json or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'status': 'error', 'message': 'กรุณาระบุข้อความคำถามทดสอบ'}), 400

    retriever = get_semantic_retriever()
    match_result = retriever.retrieve(query)

    if match_result:
        return jsonify({
            'status': 'matched',
            'matched': True,
            'id': match_result.get('id'),
            'title': match_result.get('title'),
            'intent': match_result.get('intent'),
            'score': match_result.get('score'),
            'score_percent': round(match_result.get('score', 0) * 100, 1),
            'reply': match_result.get('reply'),
            'speech': match_result.get('speech'),
            'suggestions': match_result.get('suggestions', []),
            'source': 'semantic_rag_local'
        })
    else:
        # ดึง Top-3 ใกล้เคียงที่สุด เพื่อช่วยบอกเหตุผล
        top_k = retriever.retrieve_top_k(query, k=3)
        return jsonify({
            'status': 'unmatched',
            'matched': False,
            'message': 'ไม่พบหัวข้อที่คะแนนความคล้ายคลึงผ่านเกณฑ์ (Threshold < 0.30)',
            'top_candidates': [
                {
                    'id': item.get('id'),
                    'title': item.get('title'),
                    'score': item.get('score')
                } for item in top_k
            ]
        })



# ---------------------------------------------------------------------------
# คำตอบจากเว็บรออนุมัติ: ครูตรวจแล้วกดเพิ่มเข้าฐานความรู้ = เรียนรู้ซ้ำจากคำถามจริงของผู้ใช้
# ---------------------------------------------------------------------------
def _strip_web_notes(item):
    """ตัดข้อความ "ข้อมูลจากเว็บ" ออกก่อนเข้าฐานความรู้ (กลายเป็นข้อมูลที่ครูตรวจแล้ว)"""
    from services import web_answer_service as was
    answer, speech = item.get('reply', ''), item.get('speech', '')
    for lead, note in was.WEB_NOTE.values():
        answer = answer.replace(note, '').strip()
        if speech.startswith(lead):
            speech = speech[len(lead):].strip()
    return answer, speech


@knowledge_bp.route('/api/kb/web-pending', methods=['GET'])
def list_web_pending():
    from services import web_answer_service as was
    items = sorted(was.list_pending(), key=lambda it: (-it.get('count', 1), it.get('created_at', '')))
    return jsonify({'status': 'success', 'items': items, 'web': was.status()})


@knowledge_bp.route('/api/kb/web-pending/<item_id>/approve', methods=['POST'])
def approve_web_pending(item_id):
    """เพิ่มคำตอบจากเว็บเข้าฐานความรู้ (แก้ข้อความได้ก่อนกดอนุมัติ) แล้ว Re-index ทันที"""
    from services import web_answer_service as was
    item = next((it for it in was.list_pending() if it['id'] == item_id), None)
    if not item:
        return jsonify({'status': 'error', 'message': 'ไม่พบรายการนี้'}), 404
    data = request.json or {}
    answer, speech = _strip_web_notes(item)
    sources = ', '.join(s.get('title', '') for s in item.get('sources', []) if s.get('title'))
    entry = {
        'intent': data.get('intent') or 'general_faq',
        'title': (data.get('title') or item['question'])[:80],
        'keywords': data.get('keywords') or [],
        'questions': data.get('questions') or [item['question']],
        'answer': (data.get('answer') or answer) + (f"\n\n📌 แหล่งข้อมูล: {sources}" if sources and not data.get('answer') else ''),
        'speech': data.get('speech') or speech,
        'suggestions': data.get('suggestions') or [],
    }
    try:
        res = kb_manager.add_entry(entry, auto_reindex=True)
    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 400
    was.pop_pending(item_id)
    res['voice_baking'] = _bake_answer_voice(spoken_text_of(res.get('entry')))
    return jsonify(res), 201


@knowledge_bp.route('/api/kb/web-pending/<item_id>', methods=['DELETE'])
def reject_web_pending(item_id):
    from services import web_answer_service as was
    if not was.pop_pending(item_id):
        return jsonify({'status': 'error', 'message': 'ไม่พบรายการนี้'}), 404
    return jsonify({'status': 'success'})
