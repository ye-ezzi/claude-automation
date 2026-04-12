/**
 * 카드뉴스 자동생성 Figma 플러그인
 *
 * 프레임 네이밍 규칙 (채널 약자는 무엇이든 OK):
 *   마스터_썸네일_AI   → Card01 (표지) 필드 순서대로
 *   마스터_본문_1_AI   → Card02 body_fields 순서대로
 *   마스터_본문_2_AI   → Card03
 *   마스터_본문_3_AI   → Card04
 *   마스터_본문_4_AI   → Card05 (4번째 본문이 있는 경우)
 *   마스터_CTA_AI      → Card05 CTA 유도문구
 *
 * 각 프레임 안 TEXT 노드를 위→아래(y좌표) 순서로 정렬 후 순서대로 채웁니다.
 */

figma.showUI(__html__, { width: 260, height: 320 });

figma.ui.postMessage({
  type: 'page-name',
  name: figma.currentPage.name
});

figma.ui.onmessage = async (msg) => {
  if (msg.type !== 'fill-frames') return;

  const { data, fieldOrder } = msg;
  let filled = 0;

  for (const node of figma.currentPage.children) {
    const name = node.name;

    // ── 썸네일 프레임 (Card01)
    if (name.includes('마스터_썸네일')) {
      filled += await fillFrame(node, 'Card01', data, fieldOrder);
      continue;
    }

    // ── 본문 프레임 (마스터_본문_N_*)
    const bodyMatch = name.match(/마스터_본문_(\d+)/);
    if (bodyMatch) {
      const n = parseInt(bodyMatch[1]);
      const cardKey = `Card${String(n + 1).padStart(2, '0')}`;
      filled += await fillFrame(node, cardKey, data, fieldOrder);
      continue;
    }

    // ── CTA 프레임
    if (name.includes('마스터_CTA')) {
      filled += await fillFrame(node, 'CTA', data, fieldOrder);
    }
  }

  if (filled > 0) {
    figma.notify(`✅ ${filled}개 텍스트 적용 완료`);
  } else {
    figma.notify('⚠️ 채울 프레임 없음 — 프레임 이름에 마스터_썸네일/마스터_본문_N/마스터_CTA 포함 필요');
  }
};

/**
 * 특정 카드의 필드값을 프레임 안 TEXT 노드에 위→아래 순으로 채운다.
 */
async function fillFrame(frameNode, cardKey, data, fieldOrder) {
  const fields = fieldOrder[cardKey];
  if (!fields || fields.length === 0) return 0;

  // 필드값 배열 생성
  // CTA는 키가 "Card05 CTA 유도문구" 형태로 직접 저장됨
  const values = fields.map(field => {
    if (cardKey === 'CTA') return data[field] || '';          // field = "Card05 CTA 유도문구"
    return data[`${cardKey} ${field}`] || '';                 // field = "섹션타이틀" 등
  });

  // TEXT 노드를 y좌표 오름차순(위→아래)으로 정렬
  const textNodes = getTextNodes(frameNode).sort(
    (a, b) => a.absoluteBoundingBox.y - b.absoluteBoundingBox.y
  );

  let count = 0;
  for (let i = 0; i < Math.min(textNodes.length, values.length); i++) {
    if (!values[i]) continue;
    try {
      await figma.loadFontAsync(textNodes[i].fontName);
      textNodes[i].characters = String(values[i]);
      count++;
    } catch (e) {
      console.error(`폰트 로드 실패 (${frameNode.name}):`, e);
    }
  }
  return count;
}

function getTextNodes(node) {
  const results = [];
  if (node.type === 'TEXT') results.push(node);
  if ('children' in node) {
    for (const child of node.children) {
      results.push(...getTextNodes(child));
    }
  }
  return results;
}
