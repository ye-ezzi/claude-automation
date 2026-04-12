/**
 * 카드뉴스 자동생성 Figma 플러그인 — 메인 로직
 *
 * ui.html에서 생성된 카드 내용을 받아
 * 현재 선택된 프레임(또는 전체 페이지)의 텍스트 레이어에 채워 넣습니다.
 *
 * ── 레이어 네이밍 규칙 ──────────────────────────────────────────
 *  Card01_헤드라인     Card01_컬러칩
 *  Card02_섹션타이틀   Card02_섹션텍스트   Card02_키워드   Card02_인풋텍스트
 *  Card03_*           Card04_*            (동일 구조)
 *  Card05_CTA
 *  컨셉               기대반응
 *
 * 서버 응답 키(예: "Card02 섹션타이틀")를 언더스코어 버전(Card02_섹션타이틀)으로
 * 정규화하여 레이어를 찾습니다.
 * ────────────────────────────────────────────────────────────────
 */

figma.showUI(__html__, { width: 300, height: 520 });

figma.ui.onmessage = async (msg) => {
  if (msg.type !== 'fill-frames') return;

  const data = msg.data; // { "Card02 섹션타이틀": "...", ... }

  // 서버 키 → Figma 레이어명 변환 (공백 → 언더스코어)
  const layerMap = {};
  for (const [key, value] of Object.entries(data)) {
    const layerName = key.replace(/ /g, '_');
    layerMap[layerName] = value;
  }

  // CTA 키 별칭 처리 ("Card05 CTA 유도문구" → "Card05_CTA")
  if (layerMap['Card05_CTA_유도문구']) {
    layerMap['Card05_CTA'] = layerMap['Card05_CTA_유도문구'];
  }

  // 탐색 범위: 선택된 노드 우선, 없으면 현재 페이지 전체
  const roots =
    figma.currentPage.selection.length > 0
      ? figma.currentPage.selection
      : figma.currentPage.children;

  let filled = 0;
  let missed = [];

  for (const root of roots) {
    filled += await fillNode(root, layerMap);
  }

  // 채워지지 않은 레이어 파악
  for (const layerName of Object.keys(layerMap)) {
    if (layerMap[layerName]) {
      const found = findByName(
        figma.currentPage.selection.length > 0
          ? figma.currentPage.selection
          : figma.currentPage.children,
        layerName
      );
      if (!found) missed.push(layerName);
    }
  }

  if (missed.length > 0) {
    console.log('레이어를 찾지 못했습니다:', missed);
  }

  figma.notify(`✅ ${filled}개 텍스트 채움 완료`);
};

/**
 * 재귀로 노드를 탐색하며 이름이 일치하는 텍스트 레이어에 내용을 채운다.
 * @returns {number} 채워진 레이어 수
 */
async function fillNode(node, layerMap) {
  let count = 0;
  const layerName = node.name.trim();

  if (node.type === 'TEXT' && layerMap[layerName] !== undefined) {
    await figma.loadFontAsync(node.fontName);
    node.characters = String(layerMap[layerName]);
    count++;
  }

  if ('children' in node) {
    for (const child of node.children) {
      count += await fillNode(child, layerMap);
    }
  }

  return count;
}

/**
 * 주어진 노드 배열에서 이름이 일치하는 첫 번째 노드를 반환 (재귀)
 */
function findByName(nodes, name) {
  for (const node of nodes) {
    if (node.name.trim() === name) return node;
    if ('children' in node) {
      const found = findByName(node.children, name);
      if (found) return found;
    }
  }
  return null;
}
