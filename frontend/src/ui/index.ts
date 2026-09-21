/**
 * 这个库自己的界面组件。**这里是界面长相的唯一来源** —— 不引现成的组件库,外观与组件都在这个目录里。
 * 外观三层:`palette.css` 原始值 → `semantic.css` 用途名(`--pn-surface` 等)→ `tokens.css` 用 `@theme inline` 翻成类名。
 * 组件里只用类名,别写 `var(--color-accent)`。改组件前先读:能用浏览器自己的控件就用;不写浮层(删除确认做成行内确认)。
 * 聚焦样式只在 `tokens.css` 写一次;组件不碰地址、不发请求;默认 `type="button"`;校验不在这里,由后端说。新组件照 `Button.vue` 写。
 */

export { default as Alert } from "./Alert.vue";
export { default as Avatar } from "./Avatar.vue";
export { default as Button } from "./Button.vue";
export { default as Center } from "./Center.vue";
export { default as CloseButton } from "./CloseButton.vue";
export { default as Container } from "./Container.vue";
export { default as Cover } from "./Cover.vue";
export { default as Empty } from "./Empty.vue";
export { default as FormField } from "./FormField.vue";
export { default as Heading } from "./Heading.vue";
export { default as Input } from "./Input.vue";
export { default as List } from "./List.vue";
export { default as ListItem } from "./ListItem.vue";
export { default as NumberInput } from "./NumberInput.vue";
export { default as Pagination } from "./Pagination.vue";
export { default as Popconfirm } from "./Popconfirm.vue";
export { default as SegmentedControl } from "./SegmentedControl.vue";
export { default as Select } from "./Select.vue";
export { default as Spinner } from "./Spinner.vue";
export { default as Tag } from "./Tag.vue";
export { default as TagsInput } from "./TagsInput.vue";
export { default as Text } from "./Text.vue";
export { default as Textarea } from "./Textarea.vue";
