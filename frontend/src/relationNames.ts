/**
 * 作品关系的名字:后端存的词(related / side_story / adaptation …)→ 画在页面上的名字。
 *
 * **就这一份**:家族预览与「另立为独立的作品」都要画它,各写一遍迟早会漂开 ——
 * 那种漂开不会报错,只会让同一段关系在两处显示成两个说法。
 *
 * **与后端的 `app/sources/family.py` 的 `RELATION_TYPES` 是一对**:那边管「来源的原话 → 存哪一类」,
 * 这里管「存的那一类 → 画什么字」。加一类时两处都要加,认不出时原样显示取值,不拦住页面。
 */

/** 类别 → 给人看的名字。 */
const LABELS: Record<string, string> = {
  related: "相关",
  adaptation: "改编",
  variant: "不同版本",
  side_story: "番外篇",
  prequel: "前传",
  sequel: "续集",
  spin_off: "外传",
  same_setting: "相同世界观",
  collection: "合集",
  volume: "卷",
  unknown: "说不清",
};

/** 一个关系类别画在页面上的名字;不认识时原样返回取值。 */
export function relationLabelOf(value: string): string {
  return LABELS[value] ?? value;
}
