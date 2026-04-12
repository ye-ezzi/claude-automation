/**
 * 카드뉴스 자동생성 Figma 플러그인
 *
 * 프레임 네이밍 규칙:
 *   마스터_본문_1_재테크 → Card02 데이터
 *   마스터_본문_2_재테크 → Card03 데이터
 *   마스터_본문_3_재테크 → Card04 데이터
 *
 * 각 프레임 안 텍스트레이어를 위→아래(y좌표) 순으로 정렬해서
 * config.yaml body_fields 순서대로 채웁니다.
 */

figma.showUI(__html__, { width: 260, height: 320 });

// 현재 페이지 이름을 UI로 전달 (채널 자동 감지)
figma.ui.postMessage({
  type: 'page-name',
  name: figma.currentPage.name
});

figma.ui.onmessage = async (msg) => {
  if (msg.type !== 'fill-frames') return;

  const { data, fieldOrder } = msg;
  let filled = 0;
  let skipped = [];

  for (const node of figma.currentPage.children) {
    // 마스터_본문_N_채널명 패턴 매칭
    const match = node.name.match(/마스터_본문_(\d+)_/);
    if (!match) continue;

    const n = parseInt(match[1]);
    // 본문 1 → Card02, 본문 2 → Card03, 본문 3 → Card04
    const cardKey = `Card${String(n + 1).padStart(2, '0')}`;
    const fields = fieldOrder[cardKey];

    if (!fields || fields.length === 0) {
      skipped.push(node.name);
      continue;
    }

    // 해당 카드의 필드값을 순서대로 배열로 만들기
    const values = fields.map(field => data[`${cardKey} ${field}`] || '');

    // 프레임 안 TEXT 노드를 y좌표 기준 위→아래 정렬
    const textNodes = getTextNodes(node).sort(
      (a, b) => a.absoluteBoundingBox.y - b.absoluteBoundingBox.y
    );

    // 순서대로 채우기
    for (let i = 0; i < Math.min(textNodes.length, values.length); i++) {
      if (values[i]) {
        try {
          await figma.loadFontAsync(textNodes[i].fontName);
          textNodes[i].characters = String(values[i]);
          filled++;
        } catch (e) {
          console.error(`폰트 로드 실패 (${node.name}):`, e);
        }
      }
    }
  }

  if (filled > 0) {
    figma.notify(`✅ ${filled}개 텍스트 적용 완료`);
  } else {
    figma.notify('⚠️ 채울 프레임 없음 — 프레임 이름 확인: 마스터_본문_1_재테크');
  }
};

function getTextNodes(node) {
  const results = [];
  if (node.type === 'TEXT') {
    results.push(node);
  }
  if ('children' in node) {
    for (const child of node.children) {
      results.push(...getTextNodes(child));
    }
  }
  return results;
}
