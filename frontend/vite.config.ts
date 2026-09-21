import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

// 后端的地址。默认 8011;后端临时跑在别的端口上时,用环境变量指过去:
//
//     $env:VITE_API_TARGET='http://127.0.0.1:8013'; npm run dev
//
// 留着这个口子是因为它踩过一次:后端换了端口,页面却还去敲旧的,而现象只是「读不到」
// —— 一个能改的变量比一句「记得改配置」可靠。
const target = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8011";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    // 后端在 8011,前端开发服务器在另一个端口。浏览器只认「同源」,所以把 /api
    // 这一段转给后端:页面上发出去的请求还是打给自己,跨域这件事就不存在了。
    //
    // 这一步不能省,也不能靠给后端加 CORS 来省 —— 那要改后端,而这里是前端自己
    // 的事。构建出来的产物由后端一起发时,这一段也不参与。
    proxy: {
      "/api": target,
    },
  },
});
