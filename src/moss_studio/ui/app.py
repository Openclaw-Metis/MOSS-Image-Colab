"""Gradio workbench; client-only callbacks use the authenticated HTTP adapter."""

import hashlib
import json
import os
from pathlib import Path

import gradio as gr

from moss_studio.ui.control_component import CONTROL_HTML
from moss_studio.ui.edit_component import EDIT_HTML
from moss_studio.ui.inpaint_component import INPAINT_HTML
from moss_studio.ui.layout_component import LAYOUT_HTML
from moss_studio.ui.models_component import MODELS_HTML
from moss_studio.ui.workbench_parts import GALLERY_HTML, WORKBENCH_CSS, result_panel, status_line

PROJECT_MENU_HTML = """
<div id="project-menu" style="display:flex;flex-direction:column;gap:8px">
 <label>目前專案名稱 <input id="project-name" maxlength="120"></label>
 <button id="project-rename" type="button">儲存名稱</button>
 <label>開啟其他專案 <select id="project-list"><option value="">（載入中）</option></select></label>
 <button id="project-open" type="button">開啟選取的專案</button>
 <a id="project-export" class="moss-button" download>匯出目前專案（ZIP，可在新的 Colab 續編）</a>
 <label>匯入專案 ZIP <input id="project-import" type="file" accept=".zip,application/zip"></label>
 <button id="project-delete" type="button" class="moss-danger">刪除目前專案</button>
 <p id="project-menu-status" role="status" class="moss-muted">
  專案檔含素材、遮罩、排版與作品；不含模型與密碼。匯入會建立新專案，不覆蓋現有專案。</p>
</div>
"""


# One-click sizes, about 1 MP like the model's usual working size. Every side is a multiple of
# 16 because EmptyFlux2LatentImage allocates height // 16 × width // 16 latent cells; 4:3, 3:2 and
# 16:9 are exact ratios. The sliders stay for any other size.
ASPECT_PRESETS = {
    "1:1": (1024, 1024),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
    "3:2": (1248, 832),
    "2:3": (832, 1248),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
}
ASPECT_CHOICES = [(key, key) for key in ASPECT_PRESETS] + [("自訂", "custom")]


# AC-19 batch A (2026-11-07): 7/10 zh-TW layouts fully correct, below the 8/10 gate. The spec
# requires stating the limit where titles are written; see docs/evidence/stage2-batch-a.
ZH_TW_NOTICE = (
    '<p role="note" class="moss-notice">'
    "繁體中文標題可能寫錯：實測 10 張中有 3 張出錯（近形字替換，或把框描述的字寫進標題）。"
    "請逐字檢查；框描述避免寫顏色等可能被畫成文字的詞，重要標題可改用後製加字。</p>"
)


def tab_loader(service, module: str, handle: str) -> str:
    """Client-only select hook: lazy-import the tab module, then (re)bind it to the DOM."""
    version = hashlib.sha256(
        (service.repository / "src/moss_studio/ui/static" / module).read_bytes()
    ).hexdigest()[:12]
    return (
        f"async()=>{{await import('/static/{module}?v={version}');await window.{handle}.init();}}"
    )


def build_ui(service):
    version = hashlib.sha256(
        (service.repository / "src/moss_studio/ui/static/studio.js").read_bytes()
    ).hexdigest()[:12]
    with gr.Blocks(title="MOSS-Image 創作工作台", analytics_enabled=False) as demo:
        gr.HTML(
            f"<style>{WORKBENCH_CSS}</style><h1>MOSS-Image 創作工作台</h1>"
            '<p id="moss-runtime" role="status">正在讀取執行環境…</p>'
        )
        with gr.Tabs():
            with gr.Tab("文生圖與排版") as t2i_tab:
                with gr.Row():
                    with gr.Column(scale=4):
                        prompt = gr.Textbox(
                            label="想要的畫面與文字",
                            lines=5,
                            placeholder="例如：米白色山景旅遊海報，標題為「山間慢旅」。",
                        )
                        layout_on = gr.Checkbox(label="啟用畫框排版", value=False)
                        aspect = gr.Radio(
                            choices=ASPECT_CHOICES,
                            value="1:1",
                            label="畫面比例（約 1 MP；下方寬高可微調，以 16 像素為單位）",
                        )
                        # Sides step by 16: the model works in 16×16 px cells and the engine
                        # floors anything else, so the result would not match the setting.
                        with gr.Row():
                            width = gr.Slider(512, 4096, value=1024, step=16, label="寬度")
                            height = gr.Slider(512, 4096, value=1024, step=16, label="高度")
                        profile = gr.Radio(
                            choices=[("精細 50 步", "quality50_v1"), ("加速 8 步", "fast8_v1")],
                            value="quality50_v1",
                            label="繪製方式",
                        )
                        gr.HTML('<p id="moss-profile-summary">SFT bf16</p>')
                        gr.HTML('<div id="moss-lora" hidden></div>')
                        gr.HTML(ZH_TW_NOTICE)
                        with gr.Accordion("進階設定", open=False):
                            negative = gr.Textbox(label="負向提示詞", value="")
                            seed = gr.Textbox(label="種子（留空自動產生）", value="")
                            gr.Markdown(
                                "排版 JSON 可在畫布下方展開；排版模式以 summary.caption 為準。"
                            )
                        generate = gr.Button(
                            "產生圖片",
                            variant="primary",
                            elem_id="moss-generate",
                            elem_classes="moss-cta",
                        )
                        cancel = gr.Button("取消目前工作", elem_id="moss-cancel")
                        gr.HTML('<p class="moss-shortcut">Ctrl+Enter 也可送出</p>')
                        with gr.Accordion("專案", open=False):
                            new_project = gr.Button("新建創作")
                            gr.HTML(PROJECT_MENU_HTML)
                    with gr.Column(scale=7):
                        gr.HTML(
                            status_line("moss-status", "請輸入創作內容，再按產生圖片。")
                            + '<p class="moss-muted">專案：<span id="moss-project">尚未開啟專案'
                            '</span>　<span id="moss-save-state"></span></p>'
                            '<div id="moss-view-controls" style="display:none">'
                            '<button id="moss-edit-layout" type="button">編輯排版</button>　'
                            '<button id="moss-view-result" type="button" disabled>查看作品'
                            "</button></div>"
                        )
                        gr.HTML(LAYOUT_HTML)
                        gr.HTML(
                            result_panel(
                                "moss", "生成結果", "還沒有作品。輸入描述後按「產生圖片」。"
                            )
                        )
            with gr.Tab("多圖指令修圖") as edit_tab:
                gr.HTML(EDIT_HTML)
            # Coming back from the model tab: show the backbone that is now active.
            t2i_tab.select(fn=None, js="async()=>{await window.mossStudio?.refreshSession();}")
            edit_tab.select(fn=None, js=tab_loader(service, "edit.js", "mossEdit"))
            with gr.Tab("筆刷局部重繪") as inpaint_tab:
                gr.HTML(INPAINT_HTML)
            inpaint_tab.select(fn=None, js=tab_loader(service, "inpaint.js", "mossInpaint"))
            with gr.Tab("視覺與深度控制") as control_tab:
                gr.HTML(CONTROL_HTML)
            control_tab.select(fn=None, js=tab_loader(service, "control.js", "mossControl"))
            with gr.Tab("模型與高解析") as models_tab:
                gr.HTML(MODELS_HTML)
            models_tab.select(fn=None, js=tab_loader(service, "models.js", "mossModels"))
        gr.HTML(GALLERY_HTML)
        form = [prompt, negative, width, height, seed, layout_on, profile]
        presets = json.dumps({key: list(size) for key, size in ASPECT_PRESETS.items()})
        with_aspect = f"[...v,window.mossStudio.aspectOf(v,{presets})]"
        demo.load(
            fn=None,
            outputs=[*form, aspect],
            js=(
                f"async()=>{{await import('/static/studio.js?v={version}');"
                f"const v=await window.mossStudio.init();return {with_aspect};}}"
            ),
        )
        for component in form:
            if component is width or component is height:
                # Applied at once (no confirm step); the ratio picker follows the sliders.
                component.input(
                    fn=None,
                    inputs=form,
                    outputs=aspect,
                    js=f"(...v)=>{{window.mossStudio.touch(v);return {with_aspect}.at(-1);}}",
                )
            else:
                component.input(
                    fn=None, inputs=form, js="(...values)=>window.mossStudio.touch(values)"
                )
        aspect.input(
            fn=None,
            inputs=[aspect, *form],
            outputs=[width, height],
            js=f"(a,...v)=>window.mossStudio.applyAspect(a,v,{presets})",
        )
        generate.click(
            fn=None, inputs=form, js="async(...values)=>{await window.mossStudio.submit(values);}"
        )
        cancel.click(fn=None, js="async()=>{await window.mossStudio.cancel();}")
        new_project.click(
            fn=None,
            outputs=[*form, aspect],
            js=f"async()=>{{const v=await window.mossStudio.newProject();return {with_aspect};}}",
        )
    return demo


def main():
    import argparse

    import uvicorn

    from moss_studio.adapters.http import create_http_app
    from moss_studio.services.studio import StudioService

    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("/content/moss-studio"))
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--model-root", type=Path, default=Path("/content/models"))
    args = parser.parse_args()
    service = StudioService(args.repository, args.data_root, model_root=args.model_root)
    app = create_http_app(service, os.environ.pop("MOSS_STUDIO_PASSWORD", ""), build_ui)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
