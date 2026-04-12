/**
 * 카드뉴스 자동생성 Figma 플러그인
 *
 * 동작 방식:
 *   1. 현재 페이지 이름으로 채널 자동 감지
 *   2. 구글 시트에서 "완료" 상태인 행 전체를 가져옴
 *   3. 마스터 프레임(마스터_썸네일, 마스터_본문_N, 마스터_CTA)을 복제
 *   4. 복제된 프레임에 시트 내용을 위→아래 순으로 채움
 *   5. 완료된 행마다 새 프레임 세트가 생성됨
 */

figma.showUI(__html__, { width: 260, height: 240 });

// 현재 페이지 이름에서 채널명 추출
const rawName = figma.currentPage.name;
const channelName = rawName.includes('_') ? rawName.split('_').pop() : rawName;

figma.ui.postMessage({ type: 'page-name', name: channelName });

figma.ui.onmessage = async (msg) => {
  if (msg.type !== 'generate') return;

  const { rows, fieldOrder } = msg;
  if (!rows || rows.length === 0) {
    figma.notify('⚠️ 완료된 항목이 없습니다.');
    return;
  }

  // 마스터 프레임 수집 (복제 원본)
  const masters = collectMasters();
  if (masters.length === 0) {
    figma.notify('⚠️ 마스터 프레임을 찾을 수 없습니다. (마스터_썸네일/마스터_본문_N/마스터_CTA)');
    return;
  }

  // 마스터 프레임들의 전체 너비 계산 (간격 포함)
  const GAP = 40;
  const masterSetWidth = getMasterSetWidth(masters) + GAP;

  // 마스터 세트의 맨 오른쪽 x좌표 계산 (복제본을 그 다음에 배치)
  let offsetX = getMasterSetRight(masters) + GAP;

  let totalFilled = 0;

  for (const rowData of rows) {
    const folder = rowData['폴더명'] || '';

    // 마스터 프레임 세트 복제
    const clones = [];
    for (const master of masters) {
      const clone = master.clone();
      clone.x = master.x + offsetX;
      clone.name = clone.name.replace('마스터_', `${folder}_`);
      figma.currentPage.appendChild(clone);
      clones.push({ clone, master });
    }

    // 각 복제 프레임에 데이터 채우기
    for (const { clone, master } of clones) {
      const cardKey = getCardKey(master.name);
      if (!cardKey) continue;
      totalFilled += await fillFrame(clone, cardKey, rowData, fieldOrder);
    }

    // 시트 상태 → "완료" 업데이트
    figma.ui.postMessage({
      type: 'update-status',
      channel: channelName,
      folder: folder
    });

    offsetX += masterSetWidth;
  }

  figma.notify(`✅ ${rows.length}개 항목 생성 완료 (${totalFilled}개 텍스트 채움)`);
};

/** 현재 페이지에서 마스터 프레임 수집 (이름순 정렬) */
function collectMasters() {
  return figma.currentPage.children
    .filter(n => n.name.includes('마스터_'))
    .sort((a, b) => a.x - b.x);
}

/** 마스터 프레임 세트의 전체 가로 너비 */
function getMasterSetWidth(masters) {
  if (masters.length === 0) return 0;
  const minX = Math.min(...masters.map(m => m.x));
  const maxX = Math.max(...masters.map(m => m.x + m.width));
  return maxX - minX;
}

/** 마스터 세트의 맨 오른쪽 x */
function getMasterSetRight(masters) {
  if (masters.length === 0) return 0;
  return Math.max(...masters.map(m => m.x + m.width));
}

/** 프레임 이름으로 카드 키 결정 */
function getCardKey(name) {
  if (name.includes('마스터_썸네일') || name.includes('_썸네일_')) return 'Card01';
  if (name.includes('마스터_CTA') || name.includes('_CTA_')) return 'CTA';
  const m = name.match(/본문_(\d+)/);
  if (m) return `Card${String(parseInt(m[1]) + 1).padStart(2, '0')}`;
  return null;
}

/** 프레임 안 TEXT 노드를 위→아래 순으로 채움 */
async function fillFrame(frameNode, cardKey, data, fieldOrder) {
  const fields = fieldOrder[cardKey];
  if (!fields || fields.length === 0) return 0;

  const values = fields.map(field =>
    cardKey === 'CTA' ? (data[field] || '') : (data[`${cardKey} ${field}`] || '')
  );

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
      console.error(`폰트 로드 실패:`, e);
    }
  }
  return count;
}

function getTextNodes(node) {
  const results = [];
  if (node.type === 'TEXT') results.push(node);
  if ('children' in node) {
    for (const child of node.children) results.push(...getTextNodes(child));
  }
  return results;
}
