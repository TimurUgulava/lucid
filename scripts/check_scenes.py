#!/usr/bin/env python3
"""Проверка сцен видео lucid в безголовом Chromium по реальным длительностям озвучки.

Для каждой сцены из scenes.json:
  • контракт времени: lucidPrepare() и lucidSeek(ms) есть, зависимости появления
    разрешаются без ошибок (неизвестный id, скрытый родитель, цикл — ошибка);
  • загрузка шрифтов (без незаметной подмены) и картинок;
  • в финальном состоянии: размер текста после всех преобразований, выход за кадр,
    текст на тексте, текст на линиях и стрелках, непредусмотренные пересечения линий
    между собой (узлы ветвления помечаются data-junction), наконечник стрелки, заходящий
    за изгиб собственной линии (с учётом markerUnits, viewBox, refX и толщины штриха),
    выход за карточку и отступ от её края, перекрытие текста более поздним слоем,
    контраст с фактической поверхностью, конечные точки в коротких подписях
    (предупреждение);
  • по состояниям во времени: старт, вокруг каждого появления, середина и конец
    перехода, самое плотное состояние, финал — наложения и выход за кадр;
  • детерминизм: повторный lucidPrepare() и перемотка туда-обратно дают то же;
  • подписи с data-after появляются не раньше полной видимости своих объектов.
С --video проверяется экспорт: потоки, длительность против суммы сцен,
декодирование без ошибок.

Отчёт JSON: сцена, время, элементы, причина. Список «нужен осмотр» — то, что
автоматически не решается (фон из картинки или градиента). Код выхода 1 при
дефектах, 2 при ошибке запуска.
"""
import argparse
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

QA_JS = r"""
(cfg) => {
  const W = innerWidth, H = innerHeight, S = cfg.scale;
  const MIN = cfg.minText * S, GAP = cfg.lineGap * S, PAD = cfg.cardPad * S;
  const SVGNS = 'http://www.w3.org/2000/svg';
  const effOpacity = el => { let o = 1; for (let n = el; n && n.nodeType === 1; n = n.parentElement) { const s = getComputedStyle(n); if (s.display === 'none' || s.visibility === 'hidden') return 0; o *= parseFloat(s.opacity); } return o; };
  const inClosedDetails = el => { const d = el.closest('details'); return !!(d && !d.open && !el.closest('summary')); };
  const present = el => !inClosedDetails(el) && !el.closest('[hidden]') && effOpacity(el) > cfg.presentOpacity;
  const isDecor = el => { for (let n = el; n && n.nodeType === 1; n = n.parentElement) if (n.hasAttribute('data-decor')) return true; return false; };
  const inDefs = el => !!el.closest('defs, marker, clipPath, mask, pattern');
  const textRect = el => { if (el.namespaceURI === SVGNS) return el.getBoundingClientRect(); const r = document.createRange(); r.selectNodeContents(el); const b = r.getBoundingClientRect(); return b.width ? b : el.getBoundingClientRect(); };
  const ownText = el => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const htmlText = [...document.querySelectorAll('body *')].filter(el => el.namespaceURI !== SVGNS && el.tagName !== 'SCRIPT' && el.tagName !== 'STYLE' && ownText(el));
  const svgText = [...document.querySelectorAll('svg text')].filter(el => el.textContent.trim() && !inDefs(el));
  const texts = htmlText.concat(svgText).filter(el => present(el) && !isDecor(el))
    .map(el => ({ el, r: textRect(el), text: el.textContent.trim().replace(/\s+/g, ' ').slice(0, 60) }))
    .filter(t => t.r.width > 0 && t.r.height > 0);
  const inter = (a, b, m) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > m && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > m;
  const blockOf = el => el.namespaceURI === SVGNS ? null : el.closest('h1,h2,h3,h4,p,li,figcaption');
  const related = (a, b) => a.contains(b) || b.contains(a) || (blockOf(a) && blockOf(a) === blockOf(b));
  const name = el => { if (el.id) return '#' + el.id; const anc = el.parentElement && el.parentElement.closest('[id]'); return (anc ? '#' + anc.id + '>' : '') + el.tagName.toLowerCase(); };
  const res = { smallText: [], textOverlaps: [], lineOverlaps: [], lineCrossings: [], arrowheads: [], cardOverflow: [], occlusion: [], lowContrast: [], outside: [], punctuation: [], needsEyes: [], textCount: texts.length };
  for (const t of texts) if (t.r.left < -1 || t.r.top < -1 || t.r.right > W + 1 || t.r.bottom > H + 1) res.outside.push(t.text);
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const a = texts[i], b = texts[j]; if (related(a.el, b.el)) continue;
    const m = Math.max(2, 0.12 * Math.min(a.r.height, b.r.height));
    if (inter(a.r, b.r, m)) res.textOverlaps.push([a.text, b.text]);
  }
  const rgb = s => { const m = (s || '').match(/[\d.]+/g) || []; if (m.length < 3) return null; const v = m.slice(0, 3).map(Number); return v.concat(m.length > 3 ? Number(m[3]) : 1); };
  const shapes = [...document.querySelectorAll('body *')]
    .filter(el => el.tagName !== 'SCRIPT' && el.tagName !== 'STYLE' && !/^(text|tspan|textPath)$/i.test(el.tagName) && !inDefs(el) && present(el)).map(el => {
      const svg = el.namespaceURI === SVGNS; let kind = null, color = null; const s = getComputedStyle(el);
      if (el.tagName === 'IMG') kind = 'image';
      else if (svg) { if (/^(rect|circle|ellipse|polygon|path)$/i.test(el.tagName) && s.fill && s.fill !== 'none') { color = rgb(s.fill); if (color && color[3] > 0) kind = 'svg'; } else if (/^image$/i.test(el.tagName)) kind = 'image'; }
      else { if (s.backgroundImage && s.backgroundImage !== 'none') kind = 'image'; else { color = rgb(s.backgroundColor); if (color && color[3] > 0) kind = 'html'; } }
      return kind ? { el, kind, color, r: el.getBoundingClientRect(), decor: isDecor(el) } : null;
    }).filter(Boolean);
  const shapeByEl = new Map(shapes.map(x => [x.el, x]));
  const lines = [...document.querySelectorAll('svg line, svg path, svg polyline, svg polygon')]
    .filter(el => !inDefs(el) && !isDecor(el) && !el.hasAttribute('data-under') && present(el) && typeof el.getTotalLength === 'function')
    .filter(el => { const s = getComputedStyle(el); return s.stroke && s.stroke !== 'none' && parseFloat(s.strokeWidth) > 0 && (s.fill === 'none' || s.fill === 'rgba(0, 0, 0, 0)'); });
  const coveredAt = (line, x, y) => {
    /* линия в этой точке закрыта более поздней непрозрачной фигурой? */
    const st = document.elementsFromPoint(Math.min(W - 1, Math.max(0, x)), Math.min(H - 1, Math.max(0, y)));
    for (const el of st) {
      if (el === line) return false;
      if (el.namespaceURI === SVGNS && /^(text|tspan)$/i.test(el.tagName)) continue;
      const sh = shapeByEl.get(el); if (!sh || sh.decor) continue;
      if (sh.kind === 'image' || (sh.color && sh.color[3] >= 0.9)) return (line.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
    }
    return false;
  };
  for (const line of lines) {
    let len; try { len = line.getTotalLength(); } catch (e) { continue; }
    if (!len) continue; const m = line.getScreenCTM(); if (!m) continue;
    const step = Math.max(2, len / 500);
    for (const t of texts) {
      if (related(line, t.el) || t.el.hasAttribute('data-on-line')) continue;
      let hit = false;
      for (let d = 0; d <= len; d += step) { const p = line.getPointAtLength(d); const q = new DOMPoint(p.x, p.y).matrixTransform(m); if (q.x >= t.r.left - GAP && q.x <= t.r.right + GAP && q.y >= t.r.top - GAP && q.y <= t.r.bottom + GAP && !coveredAt(line, q.x, q.y)) { hit = true; break; } }
      if (hit) res.lineOverlaps.push({ text: t.text, line: name(line) });
    }
  }
  /* Пересечения линий между собой: линии одного узла ветвления помечаются data-junction (на линии или группе) */
  const junctionOf = el => { const j = el.closest('[data-junction]'); if (!j) return null; const v = j.getAttribute('data-junction'); return v ? 'name:' + v : 'el:' + (j.id || Math.random()); };
  /* точки пути; разрыв между подпутями (несколько M) помечается null, чтобы не соединять их ложным отрезком */
  const samples = line => { const out = []; let len; try { len = line.getTotalLength(); } catch (e) { return out; } if (!len) return out; const m = line.getScreenCTM(); if (!m) return out; const n = Math.max(8, Math.min(600, Math.ceil(len / 3))); const step = len / n; let prev = null; for (let i = 0; i <= n; i++) { const p = line.getPointAtLength(len * i / n); const q = new DOMPoint(p.x, p.y).matrixTransform(m); const pt = [q.x, q.y]; if (prev && Math.hypot(pt[0] - prev[0], pt[1] - prev[1]) > step * Math.hypot(m.a, m.b) * 3 + 1) out.push(null); out.push(pt); prev = pt; } return out; };
  const segInter = (a, b, c, d) => { const r = [b[0] - a[0], b[1] - a[1]], s2 = [d[0] - c[0], d[1] - c[1]]; const den = r[0] * s2[1] - r[1] * s2[0]; if (Math.abs(den) < 1e-9) return null; const t = ((c[0] - a[0]) * s2[1] - (c[1] - a[1]) * s2[0]) / den, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den; if (t < 0 || t > 1 || u < 0 || u > 1) return null; return [a[0] + t * r[0], a[1] + t * r[1]]; };
  const dist = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]);
  const strokePx = line => { const s = getComputedStyle(line); const m = line.getScreenCTM(); return parseFloat(s.strokeWidth) * (m ? Math.hypot(m.a, m.b) : 1); };
  const lineInfo = lines.map(l => ({ el: l, pts: samples(l), junction: junctionOf(l), w: strokePx(l) }));
  for (let i = 0; i < lineInfo.length; i++) for (let j = i + 1; j < lineInfo.length; j++) {
    const A = lineInfo[i], B = lineInfo[j]; if (A.pts.length < 2 || B.pts.length < 2) continue;
    if (A.junction && A.junction === B.junction) continue;
    const tol = Math.max(A.w, B.w) + 2 * S; let hit = null;
    const ends = pts => { const e = []; for (let k = 0; k < pts.length; k++) { if (pts[k] && (k === 0 || !pts[k - 1] || k === pts.length - 1 || !pts[k + 1])) e.push(pts[k]); } return e; };
    const endsA = ends(A.pts), endsB = ends(B.pts);
    for (let a = 0; a < A.pts.length - 1 && !hit; a++) for (let b = 0; b < B.pts.length - 1; b++) {
      if (!A.pts[a] || !A.pts[a + 1] || !B.pts[b] || !B.pts[b + 1]) continue;
      const x = segInter(A.pts[a], A.pts[a + 1], B.pts[b], B.pts[b + 1]); if (!x) continue;
      const nearEnd = endsA.some(e => dist(e, x) <= tol) || endsB.some(e => dist(e, x) <= tol);
      if (!nearEnd) { hit = x; break; }
    }
    if (hit) res.lineCrossings.push({ a: name(A.el), b: name(B.el), at: [Math.round(hit[0]), Math.round(hit[1])] });
  }
  /* Наконечник не должен заходить за изгиб собственной линии: последний прямой участок длиннее головки плюс зазор */
  const markerLen = (line, which) => {
    const s = getComputedStyle(line); const ref = (which === 'end' ? s.markerEnd : s.markerStart) || 'none';
    const mm = ref.match(/url\(["']?#([^"')]+)["']?\)/); if (!mm) return 0;
    const mk = document.getElementById(mm[1]); if (!mk) return 0;
    const mw = parseFloat(mk.getAttribute('markerWidth') || '3');
    const units = (mk.getAttribute('markerUnits') || 'strokeWidth') === 'strokeWidth' ? parseFloat(s.strokeWidth) || 1 : 1;
    const vb = (mk.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    const vbw = vb.length === 4 && vb[2] > 0 ? vb[2] : mw;
    const refX = parseFloat(mk.getAttribute('refX') || '0');
    const behind = which === 'end' ? refX / vbw : (vbw - refX) / vbw;
    return mw * units * Math.max(0, Math.min(1, behind));
  };
  for (const line of lines) {
    for (const which of ['end', 'start']) {
      const head = markerLen(line, which); if (!head) continue;
      let len; try { len = line.getTotalLength(); } catch (e) { continue; } if (!len) continue;
      const step = Math.max(1, len / 400); let straight = 0; let prev = null, dir = null;
      for (let d = 0; d <= len; d += step) {
        const dd = which === 'end' ? len - d : d; const p = line.getPointAtLength(dd);
        if (prev) { const v = [p.x - prev.x, p.y - prev.y]; const n = Math.hypot(v[0], v[1]); if (n > 0.01) { const u = [v[0] / n, v[1] / n]; if (dir) { const dot = u[0] * dir[0] + u[1] * dir[1]; if (dot < Math.cos(20 * Math.PI / 180)) break; } else dir = u; } }
        straight = d; prev = p;
      }
      const sw = parseFloat(getComputedStyle(line).strokeWidth) || 1;
      const need = head + Math.max(sw, 2);
      if (straight < len - 0.5 && straight < need) res.arrowheads.push({ line: name(line), end: which, arm: Math.round(straight), head: Math.round(head), need: Math.round(need) });
    }
  }

  /* (фигуры вычислены выше) */
  for (const t of texts) for (const sh of shapes) {
    if (sh.decor || related(sh.el, t.el)) continue;
    if (!(t.el.compareDocumentPosition(sh.el) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
    if (sh.kind !== 'image' && sh.color && sh.color[3] < 0.9) continue;
    if (inter(t.r, sh.r, 4)) res.occlusion.push({ text: t.text, by: name(sh.el) });
  }
  const lum = c => c.slice(0, 3).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }).reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0);
  const blend = (c, b) => c.slice(0, 3).map((v, i) => v * c[3] + b[i] * (1 - c[3])).concat(1);
  const bodyBg = rgb(getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1];
  const byEl = shapeByEl;
  for (const t of texts) {
    const s = getComputedStyle(t.el); const svg = t.el.namespaceURI === SVGNS;
    let scale = 1;
    if (svg) { const m = t.el.getScreenCTM(); if (m) scale = Math.hypot(m.a, m.b); }
    else { for (let n = t.el; n && n.nodeType === 1; n = n.parentElement) { const tr = getComputedStyle(n).transform; if (tr && tr !== 'none') { try { const mm = new DOMMatrix(tr); scale *= Math.hypot(mm.a, mm.b) || 1; } catch (e) {} } } }
    const px = parseFloat(s.fontSize) * scale;
    if (px < MIN - 0.1) res.smallText.push({ text: t.text, px: Math.round(px * 10) / 10 });
    const cx = Math.min(W - 1, Math.max(0, (t.r.left + t.r.right) / 2)), cy = Math.min(H - 1, Math.max(0, (t.r.top + t.r.bottom) / 2));
    const stack = document.elementsFromPoint(cx, cy);
    let i0 = stack.indexOf(t.el); if (i0 < 0) i0 = stack.findIndex(e => e.contains(t.el));
    let bg = null, surface = null;
    for (let i = Math.max(0, i0); i < stack.length; i++) {
      const shp = byEl.get(stack[i]); if (!shp) continue;
      if (shp.decor && shp.kind === 'image') continue; /* декоративная развёртка или узор не считается фоном */
      if (shp.kind === 'image') { bg = 'image'; surface = shp; break; }
      if (shp.color[3] >= 0.9) { bg = bg ? blend(bg, shp.color) : shp.color; surface = surface || shp; break; }
      bg = bg ? blend(bg, shp.color) : shp.color; surface = surface || shp;
    }
    if (bg === 'image') res.needsEyes.push({ text: t.text, reason: 'фон из картинки или градиента, контраст не измерить' });
    else {
      if (!bg) bg = bodyBg; else if (bg[3] < 0.9) bg = blend(bg, bodyBg);
      const fg0 = rgb(svg ? s.fill : s.color) || [0, 0, 0, 1]; const fg = blend(fg0, bg);
      const la = lum(fg), lb = lum(bg); const ratio = (Math.max(la, lb) + .05) / (Math.min(la, lb) + .05);
      if (ratio < cfg.contrast) res.lowContrast.push({ text: t.text, ratio: Math.round(ratio * 100) / 100, bg: name(surface ? surface.el : document.body) });
    }
    if (surface && surface.kind !== 'image' && !surface.decor && surface.el !== document.body && surface.el.tagName.toLowerCase() !== 'main' && (surface.el.tagName.toLowerCase() === 'rect' || surface.kind === 'html') && surface.r.width < W * 0.98) {
      const c = surface.r;
      if (t.r.left < c.left + PAD || t.r.right > c.right - PAD || t.r.top < c.top + PAD || t.r.bottom > c.bottom - PAD) res.cardOverflow.push({ text: t.text, card: name(surface.el) });
    }
    if (t.text.length < 80 && /\.$/.test(t.text) && !/\d\.$/.test(t.text) && !t.el.closest('.caption, [data-role="caption"], .note')) res.punctuation.push(t.text);
  }
  return res;
}
"""

FONT_JS = r"""
async () => {
  /* Для каждой пары гарнитура+вес берём текст самой страницы и сравниваем ширину с запасными
     семействами. Совпадение со всеми запасными — гарнитура не загрузилась или в ней нет глифов
     для письма этого текста (например, кириллицы). */
  const seen = new Map(); const out = [];
  const probe = (ff, w, txt) => { const sp = document.createElement('span'); sp.textContent = txt; sp.style.cssText = 'position:absolute;left:-9999px;top:0;font-size:48px;white-space:nowrap;font-weight:' + w + ';font-family:' + ff; document.body.appendChild(sp); const r = sp.getBoundingClientRect().width; sp.remove(); return r; };
  const same = (a, b) => Math.abs(a - b) < 0.5;
  const generic = /^(serif|sans-serif|monospace|system-ui|ui-sans-serif|ui-serif|ui-monospace|cursive|fantasy)$/i;
  for (const el of document.querySelectorAll('body *')) {
    if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') continue;
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\s+/g, ' ').trim();
    if (!own || !/\p{L}/u.test(own)) continue;
    const st = getComputedStyle(el); const fam = st.fontFamily.split(',')[0].trim().replace(/^["']|["']$/g, '');
    if (!fam || generic.test(fam)) continue;
    const key = fam + '|' + st.fontWeight; if (seen.has(key)) continue; seen.set(key, true);
    /* только буквы доминирующего письма: пробелы, цифры и знаки есть в любой гарнитуре и маскируют подмену */
    const cyr = own.match(/\p{Script=Cyrillic}/gu) || [], lat = own.match(/\p{Script=Latin}/gu) || [];
    const letters = (cyr.length >= lat.length ? cyr : lat).join('');
    if (letters.length < 3) continue;
    const txt = letters.slice(0, 30);
    /* дождаться начертания: лениво грузится при первом использовании, иначе проба меряет запасной шрифт */
    try { await document.fonts.load(st.fontWeight + ' 48px "' + fam + '"', txt + 'Wg'); } catch (e) {}
    /* запасные с заведомо разной шириной знака; родовые семейства могут совпасть по метрикам с проверяемой */
    const fb = ['"Courier New", monospace', '"Times New Roman", serif', 'Arial, sans-serif'];
    const loaded = fb.filter(g => !same(probe('"' + fam + '", ' + g, st.fontWeight, txt), probe(g, st.fontWeight, txt))).length >= 2;
    if (!loaded) {
      const lat = 'Explanation Wg 0123';
      const latinLoaded = fb.filter(g => !same(probe('"' + fam + '", ' + g, st.fontWeight, lat), probe(g, st.fontWeight, lat))).length >= 2;
      out.push({ family: fam, weight: st.fontWeight, sample: txt, reason: latinLoaded ? 'нет глифов для письма этого текста, идёт подмена' : 'не загрузилась, идёт подмена' });
    }
  }
  return out;
}
"""


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def load_durations(audio_dir, scenes):
    durations = {}
    if audio_dir:
        dp = Path(audio_dir) / "durations.json"
        if dp.exists():
            durations = json.loads(dp.read_text())
    for sc in scenes:
        sid = sc["id"]
        if sid in durations:
            continue
        wav = Path(audio_dir) / (sid + ".wav") if audio_dir else None
        if wav and wav.exists():
            durations[sid] = wav_seconds(wav)
        else:
            durations[sid] = max(3.0, len(sc.get("narration", "").split()) / 2.5)
    return durations


def check_video(video, expected_seconds):
    issues = []
    info = {}
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration",
                              "-of", "json", str(video)], capture_output=True, text=True, timeout=120)
        info = json.loads(out.stdout or "{}")
    except Exception as e:
        return [{"kind": "video", "reason": "ffprobe не отработал: {}".format(e)}], info
    streams = info.get("streams", [])
    if not any(s.get("codec_type") == "video" for s in streams):
        issues.append({"kind": "video", "reason": "нет видеопотока"})
    if not any(s.get("codec_type") == "audio" for s in streams):
        issues.append({"kind": "video", "reason": "нет аудиопотока"})
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    if expected_seconds and abs(dur - expected_seconds) > 0.75:
        issues.append({"kind": "video", "reason": "длительность {:.2f} с, ожидалось {:.2f} с".format(dur, expected_seconds)})
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    if dec.returncode != 0 or dec.stderr.strip():
        issues.append({"kind": "video", "reason": "ошибки декодирования: " + dec.stderr.strip()[:300]})
    info["decoded_without_errors"] = not dec.stderr.strip() and dec.returncode == 0
    return issues, info


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenes", required=True, help="путь к scenes.json")
    p.add_argument("--audio-dir", default="", help="папка с durations.json или <id>.wav; без неё длительность по словам")
    p.add_argument("--video", default="", help="проверить и готовый mp4")
    p.add_argument("--report", default="", help="куда положить JSON-отчёт (по умолчанию рядом со scenes.json)")
    p.add_argument("--shots", default="", help="папка для кадров финального состояния: полный и 960 px")
    p.add_argument("--only", default="", help="проверить только эти id через запятую")
    p.add_argument("--min-text", type=float, default=24.0, help="минимальный размер текста в px при высоте кадра 1080")
    p.add_argument("--contrast", type=float, default=4.5)
    p.add_argument("--line-gap", type=float, default=10.0, help="зазор от текста до линии, px при 1080")
    p.add_argument("--card-pad", type=float, default=12.0, help="внутренний отступ карточки, px при 1080")
    p.add_argument("--pad", type=float, default=0.6, help="тишина в конце сцены, секунд (как у render_video)")
    args = p.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        die("Playwright не установлен: pip3 install playwright && python3 -m playwright install chromium")

    spec_path = Path(args.scenes)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    scenes = spec["scenes"]
    only = set(args.only.split(",")) if args.only else None
    size = spec.get("design", spec.get("size", "1920x1080"))
    width, height = (int(x) for x in size.lower().split("x"))
    scale = height / 1080.0
    durations = load_durations(args.audio_dir, scenes)
    cfg = {"scale": scale, "minText": args.min_text, "lineGap": args.line_gap, "cardPad": args.card_pad,
           "contrast": args.contrast, "presentOpacity": 0.3}
    report, issues, eyes = [], [], []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        small = None
        if args.shots:
            try:
                small = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=0.5).new_page()
            except Exception:
                small = None
        page = ctx.new_page()
        for sc in scenes:
            sid = sc["id"]
            if only and sid not in only:
                continue
            html = spec_path.parent / sc["file"]
            item = {"scene": sid, "seconds": durations[sid], "errors": [], "final": {}, "states": [], "fonts": [], "dependencies": []}
            errors = []
            page.remove_listener("pageerror", lambda e: None) if False else None
            handler = lambda e, _errors=errors: _errors.append(str(e))
            page.on("pageerror", handler)
            if not html.exists():
                issues.append({"scene": sid, "kind": "файл", "reason": "нет файла сцены {}".format(html)})
                page.remove_listener("pageerror", handler)
                continue
            page.goto(html.resolve().as_uri(), wait_until="load")
            page.evaluate("document.fonts ? document.fonts.ready : null")
            page.wait_for_timeout(200)
            contract = page.evaluate("typeof window.lucidPrepare === 'function' && typeof window.lucidSeek === 'function'")
            if not contract:
                issues.append({"scene": sid, "kind": "контракт", "reason": "в сцене нет lucidPrepare/lucidSeek"})
                page.remove_listener("pageerror", handler)
                continue
            words = len(sc.get("narration", "").split())
            seconds = durations[sid]
            page.evaluate("a => { window.lucidTiming = a; }", {"words": words, "seconds": seconds})
            prep_error = page.evaluate("() => { try { window.lucidPrepare(); return ''; } catch (e) { return String(e.message || e); } }")
            if prep_error:
                issues.append({"scene": sid, "kind": "зависимости", "reason": prep_error})
                item["errors"].append(prep_error)
                report.append(item)
                page.remove_listener("pageerror", handler)
                continue
            imgs_ok = page.evaluate("() => [...document.images].every(i => i.complete && i.naturalWidth > 0)")
            if not imgs_ok:
                issues.append({"scene": sid, "kind": "картинки", "reason": "не все картинки загрузились"})
            fonts_missing = page.evaluate(FONT_JS)
            item["fonts"] = fonts_missing
            for f in fonts_missing:
                issues.append({"scene": sid, "kind": "шрифт", "reason": "гарнитура {} ({}): {} — «{}»".format(f["family"], f["weight"], f["reason"], f["sample"])})
            fade = page.evaluate("(window.lucid && window.lucid.fadeMs) || 0") / 1000.0
            events = page.evaluate("() => [...document.querySelectorAll('[data-at]')].map(e => ({ id: e.id || e.tagName.toLowerCase(), at: Number(e.dataset.at || 0) }))")
            deps = page.evaluate("""() => [...document.querySelectorAll('[data-after]')].map(el => ({
                text: el.textContent.trim().slice(0, 50), at: Number(el.dataset.at || 0), after: el.dataset.after,
                parents: el.dataset.after.split(',').map(s => s.trim()).filter(Boolean).flatMap(ref => {
                  if (ref[0] === '@') { const box = document.getElementById(ref.slice(1)); return box ? [...box.querySelectorAll('[data-at]')].filter(d => d !== el && !el.contains(d)).map(d => ({ id: d.id || d.tagName.toLowerCase(), at: Number(d.dataset.at || 0) })) : []; }
                  const d = document.getElementById(ref); return d ? [{ id: ref, at: Number(d.dataset.at || 0) }] : [];
                }) }))""")
            item["dependencies"] = deps
            for d in deps:
                for par in d["parents"]:
                    if d["at"] + 1e-3 < par["at"] + fade:
                        issues.append({"scene": sid, "kind": "подпись раньше рисунка", "reason": "«{}» в {:.2f} с, объект {} виден полностью в {:.2f} с".format(d["text"], d["at"], par["id"], par["at"] + fade)})
            end_ms = int((seconds + args.pad) * 1000)
            page.evaluate("ms => window.lucidSeek(ms)", end_ms)
            final = page.evaluate(QA_JS, cfg)
            item["final"] = final
            for kind in ("smallText", "textOverlaps", "lineOverlaps", "lineCrossings", "arrowheads", "cardOverflow", "occlusion", "lowContrast", "outside"):
                for v in final.get(kind, []):
                    issues.append({"scene": sid, "ms": end_ms, "kind": kind, "detail": v})
            for v in final.get("punctuation", []):
                item.setdefault("warnings", []).append({"kind": "punctuation", "text": v})
            for v in final.get("needsEyes", []):
                eyes.append({"scene": sid, "detail": v})
            ats = sorted(set(e["at"] for e in events))
            moments = {0, 500}
            for at in ats:
                for m in (at - 0.04, at + fade / 2, at + fade + 0.04, at + fade + 0.5):
                    moments.add(max(0, int(m * 1000)))
            moments.add(int(seconds * 1000))
            moments.add(end_ms)
            for ms in sorted(moments):
                page.evaluate("ms => window.lucidSeek(ms)", ms)
                st = page.evaluate(QA_JS, cfg)
                bad = {k: st[k] for k in ("textOverlaps", "lineOverlaps", "lineCrossings", "occlusion", "outside") if st[k]}
                item["states"].append({"ms": ms, "issues": bad})
                for k, vals in bad.items():
                    for v in vals:
                        issues.append({"scene": sid, "ms": ms, "kind": k, "detail": v})
            before = page.evaluate("() => [...document.querySelectorAll('[data-at]')].map(e => e.dataset.at)")
            page.evaluate("ms => window.lucidSeek(ms)", end_ms)
            snapA = page.evaluate("() => [...document.querySelectorAll('[data-at]')].map(e => e.style.opacity)")
            page.evaluate("() => { window.lucidPrepare(); }")
            after = page.evaluate("() => [...document.querySelectorAll('[data-at]')].map(e => e.dataset.at)")
            page.evaluate("ms => window.lucidSeek(ms)", int(end_ms / 2))
            page.evaluate("ms => window.lucidSeek(ms)", end_ms)
            snapB = page.evaluate("() => [...document.querySelectorAll('[data-at]')].map(e => e.style.opacity)")
            if before != after or snapA != snapB:
                issues.append({"scene": sid, "kind": "детерминизм", "reason": "повторный lucidPrepare или перемотка меняют состояние"})
            if errors:
                item["errors"] += errors
                for e in errors:
                    issues.append({"scene": sid, "kind": "ошибка страницы", "reason": e[:200]})
            if args.shots:
                out = Path(args.shots)
                out.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(out / (sid + ".png")))
                if small is not None:
                    try:
                        small.goto(html.resolve().as_uri(), wait_until="load")
                        small.evaluate("document.fonts ? document.fonts.ready : null")
                        small.evaluate("a => { window.lucidTiming = a; window.lucidPrepare(); }", {"words": words, "seconds": seconds})
                        small.evaluate("ms => window.lucidSeek(ms)", end_ms)
                        small.screenshot(path=str(out / (sid + "-960.png")))
                    except Exception as e:
                        item["errors"].append("960: " + str(e)[:120])
            report.append(item)
            page.remove_listener("pageerror", handler)
        browser.close()

    video_info = {}
    if args.video:
        expected = sum(durations[sc["id"]] + args.pad for sc in scenes) if not only else 0
        vissues, video_info = check_video(Path(args.video), expected)
        issues += vissues

    out = {"scenes": report, "issues": issues, "needs_eyes": eyes, "video": video_info,
           "config": {"size": size, "min_text_px": args.min_text * scale, "contrast": args.contrast}}
    rp = Path(args.report) if args.report else spec_path.parent / "scene-checks.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    grouped = {}
    for it in issues:
        key = (it.get("scene", "видео"), it["kind"], it.get("reason") or json.dumps(it.get("detail"), ensure_ascii=False))
        g = grouped.setdefault(key, {"first_ms": it.get("ms"), "count": 0})
        g["count"] += 1
    for (where, kind, detail), g in grouped.items():
        ms = " @{}мс".format(g["first_ms"]) if g["first_ms"] is not None else ""
        times = " (в {} состояниях)".format(g["count"]) if g["count"] > 1 else ""
        print("дефект: {}{}: {}: {}{}".format(where, ms, kind, detail, times))
    for e in eyes:
        print("нужен осмотр: {}: {}".format(e["scene"], json.dumps(e["detail"], ensure_ascii=False)))
    print("отчёт: {}".format(rp))
    if not issues:
        if report:
            print("ок: {} сцен без дефектов{}".format(len(report), ", {} мест на осмотр".format(len(eyes)) if eyes else ""))
        else:
            print("ок: экспорт без дефектов" if args.video else "ок: сцен для проверки не выбрано")
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
