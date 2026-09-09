#!/usr/bin/env bash
# Lädt die Bild-KI-Modelle für sd-server (FLUX) und sd-server-pony (Pony)
# nach ~/sd-test/models bzw. ~/sd-test/models-pony.
#
#   ./modelle-holen.sh flux     # nur FLUX-Set
#   ./modelle-holen.sh pony     # nur Pony-Set (inkl. ControlNet / IP-Adapter)
#   ./modelle-holen.sh all      # beides (Default)
#
# Idempotent: vorhandene Dateien mit passender Größe werden übersprungen,
# angefangene Downloads per `wget -c` fortgesetzt.
#
# Die Realism-LoRA kommt von Civitai und braucht einen API-Token:
#   export CIVITAI_TOKEN=xxxxxxxx   (https://civitai.com/user/account -> API Keys)
# Ohne Token wird nur diese eine Datei übersprungen (mit Hinweis).
set -u

FLUX_DIR="${FLUX_DIR:-$HOME/sd-test/models}"
PONY_DIR="${PONY_DIR:-$HOME/sd-test/models-pony}"
was="${1:-all}"

hole() {  # hole <zielpfad> <url> [erwartete_bytes]
  local ziel="$1" url="$2" soll="${3:-}"
  mkdir -p "$(dirname "$ziel")"
  if [[ -f "$ziel" ]]; then
    local ist; ist=$(stat -c%s "$ziel" 2>/dev/null || echo 0)
    if [[ -z "$soll" || "$ist" == "$soll" ]]; then
      echo "  ok    $(basename "$ziel")  ($ist B)"
      return 0
    fi
    echo "  teil  $(basename "$ziel")  ($ist / $soll B) -> setze fort"
  else
    echo "  lade  $(basename "$ziel")"
  fi
  wget -q --show-progress -c -O "$ziel" "$url" || { echo "  FEHLER bei $url"; return 1; }
  if [[ -n "$soll" ]]; then
    local ist; ist=$(stat -c%s "$ziel")
    [[ "$ist" == "$soll" ]] || { echo "  WARNUNG: $(basename "$ziel") $ist B, erwartet $soll B"; }
  fi
}

flux() {
  echo "== FLUX-Set -> $FLUX_DIR =="
  local HF="https://huggingface.co"
  hole "$FLUX_DIR/flux1-schnell-Q4_K_S.gguf" "$HF/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q4_K_S.gguf?download=true"       6783943712
  hole "$FLUX_DIR/clip_l.safetensors"        "$HF/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors?download=true"        447075896
  hole "$FLUX_DIR/t5xxl-Q5_K_M.gguf"         "$HF/city96/t5-v1_1-xxl-encoder-gguf/resolve/main/t5-v1_1-xxl-encoder-Q5_K_M.gguf?download=true" 3386856640
  hole "$FLUX_DIR/ae.safetensors"            "$HF/Comfy-Org/flux1-schnell/resolve/main/split_files/vae/ae.safetensors?download=true"       335304388
}

pony() {
  echo "== Pony-Set -> $PONY_DIR =="
  local HF="https://huggingface.co"
  hole "$PONY_DIR/pony-diffusion-v6-xl-Q8_0.gguf"                    "$HF/offgrid-ai/pony-diffusion-v6-xl-GGUF/resolve/main/pony-diffusion-v6-xl-Q8_0.gguf?download=true"  4180186816
  hole "$PONY_DIR/controlnet/controlnet-canny-sdxl.safetensors"      "$HF/xinsir/controlnet-canny-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors?download=true" 2502139104
  hole "$PONY_DIR/ipadapter/ip-adapter_sdxl_vit-h.safetensors"       "$HF/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl_vit-h.safetensors?download=true"           698391064
  hole "$PONY_DIR/ipadapter/ip-adapter-plus-face_sdxl_vit-h.safetensors" "$HF/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors?download=true" 847517512
  hole "$PONY_DIR/clip_vision/clip_vision_vit_h.safetensors"         "$HF/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors?download=true"                 2528373448
  hole "$PONY_DIR/clip_vision/config.json"                           "$HF/h94/IP-Adapter/resolve/main/models/image_encoder/config.json?download=true"

  local lora="$PONY_DIR/loras/Realism Lora By Stable Yogi_V3_Lite.safetensors"
  if [[ -f "$lora" ]]; then
    echo "  ok    $(basename "$lora")"
  elif [[ -n "${CIVITAI_TOKEN:-}" ]]; then
    # Civitai model version 667086 = "Realism Lora By Stable Yogi" V3 Lite (SDXL/Pony)
    hole "$lora" "https://civitai.com/api/download/models/667086?token=${CIVITAI_TOKEN}"
  else
    echo "  ÜBERSPRUNGEN: Realism-LoRA - setze CIVITAI_TOKEN und starte erneut,"
    echo "               oder lade Civitai model version 667086 manuell nach:"
    echo "               $lora"
  fi
}

case "$was" in
  flux) flux ;;
  pony) pony ;;
  all)  flux; pony ;;
  *) echo "Aufruf: $0 [flux|pony|all]"; exit 1 ;;
esac
echo "fertig."
