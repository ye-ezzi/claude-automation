/**
 * 카드뉴스 자동생성 Figma 플러그인
 *
 * 현재 Figma 페이지 이름 → 채널 자동 감지
 * 구글 시트에서 해당 채널 데이터 가져와 텍스트 레이어에 채움
 *
 * 레이어 이름은 시트 컬럼명과 동일하게 (공백 포함):
 *   "Card01 헤드라인", "Card02 섹션타이틀", "Card02 섹션텍스트" ...
 */

figma.showUI(__html__, { width: 260, height: 320 });

// 현재 페이지 이름을 UI로 전달
figma.ui.postMessage({
  type: 'page-name',
  name: figma.currentPage.name
});

figma.ui.onmessage = async (msg) => {
  if (msg.type !== 'fill-frames') return;

  const data = msg.data;
  const roots = figma.currentPage.children;

  let filled = 0;

  for (const root of roots) {
    filled += await fillNode(root, data);
  }

  figma.notify(filled > 0 ? `✅ ${filled}개 텍스트 적용 완료` : '⚠️ 일치하는 레이어 없음 — 레이어 이름 확인 필요');
};

async function fillNode(node, data) {
  let count = 0;
  const name = node.name.trim();

  if (node.type === 'TEXT') {
    // 시트 컬럼명 그대로 매칭 (공백 포함)
    // 언더스코어 버전도 함께 시도
    const underscored = name.replace(/_/g, ' ');
    const value = data[name] ?? data[underscored] ?? null;

    if (value !== null && value !== '') {
      await figma.loadFontAsync(node.fontName);
      node.characters = String(value);
      count++;
    }
  }

  if ('children' in node) {
    for (const child of node.children) {
      count += await fillNode(child, data);
    }
  }

  return count;
}
