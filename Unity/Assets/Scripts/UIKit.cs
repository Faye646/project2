using UnityEngine;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// Greybox UI helpers: everything is built from code with one rounded 9-slice sprite, in the
    /// paper-and-ink colours of the level art, until the real UI art arrives.
    /// </summary>
    public static class UIKit
    {
        public static readonly Color Paper = Hex("#f4ecd9");
        public static readonly Color Card = Hex("#e9dcbc");
        public static readonly Color CardDark = Hex("#d9c79d");
        public static readonly Color Ink = Hex("#4a3322");
        public static readonly Color InkSoft = Hex("#8a6d52");
        public static readonly Color Accent = Hex("#5d88b6");   // the blue of the door curtains
        public static readonly Color Good = Hex("#7d9d3f");
        public static readonly Color Fire = Hex("#e0822f");
        public static readonly Color Locked = Hex("#cfc6b3");

        static Sprite rounded;
        static Font font, fontBold;

        public static Color Hex(string s) => ColorUtility.TryParseHtmlString(s, out var c) ? c : Color.magenta;

        /// <summary>BianHe Sans (Noto Sans SC subset, bundled) so every platform, WebGL included, shows the same Chinese text.</summary>
        public static Font Font => font ??= LoadFont("Fonts/BianHeSans-Regular");
        public static Font FontBold => fontBold ??= LoadFont("Fonts/BianHeSans-Bold");

        static Font LoadFont(string path)
        {
            var f = Resources.Load<Font>(path);
            return f != null ? f : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }

        static Sprite circle, halfRing, halfDisc;

        /// <summary>White disc with a soft 1-px edge (wok, glow, dots), tinted by the Image colour.</summary>
        public static Sprite Circle => circle ??= MakeSprite(128, 128, (x, y) =>
        {
            float d = Mathf.Sqrt((x - 64) * (x - 64) + (y - 64) * (y - 64));
            return Mathf.Clamp01(63.5f - d);
        });

        /// <summary>Upper half of a ring, for the 火候 gauge: use with Image.Type.Filled, Radial180, origin Bottom.</summary>
        public static Sprite HalfRing => halfRing ??= MakeSprite(256, 128, (x, y) =>
        {
            float d = Mathf.Sqrt((x - 128) * (x - 128) + y * y);
            return Mathf.Clamp01(Mathf.Min(127.5f - d, d - 80f));
        });

        /// <summary>Upper half of a disc, the same size as HalfRing: the solid face behind the gauge.</summary>
        public static Sprite HalfDisc => halfDisc ??= MakeSprite(256, 128, (x, y) =>
            Mathf.Clamp01(127.5f - Mathf.Sqrt((x - 128) * (x - 128) + y * y)));

        static Sprite MakeSprite(int w, int h, System.Func<float, float, float> alpha)
        {
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
            var px = new Color32[w * h];
            for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                px[y * w + x] = new Color32(255, 255, 255, (byte)(alpha(x + 0.5f, y + 0.5f) * 255));
            tex.SetPixels32(px);
            tex.Apply();
            return Sprite.Create(tex, new Rect(0, 0, w, h), new Vector2(0.5f, 0.5f), 100);
        }

        /// <summary>A plain image with a sprite, no outline, not a raycast target unless asked.</summary>
        public static Image Img(Transform parent, string name, Sprite sprite, Color color, Vector2 anchorMin, Vector2 anchorMax,
            bool raycast = false, bool preserveAspect = false)
        {
            var rt = Rect(parent, name, anchorMin, anchorMax);
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = sprite;
            img.color = color;
            img.raycastTarget = raycast;
            img.preserveAspect = preserveAspect;
            return img;
        }

        /// <summary>White rounded rectangle, 9-sliced, tinted by the Image colour.</summary>
        public static Sprite Rounded
        {
            get
            {
                if (rounded != null) return rounded;
                const int size = 64, r = 20;
                var tex = new Texture2D(size, size, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
                var px = new Color32[size * size];
                for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    float dx = Mathf.Max(0, Mathf.Max(r - x - 0.5f, x + 0.5f - (size - r)));
                    float dy = Mathf.Max(0, Mathf.Max(r - y - 0.5f, y + 0.5f - (size - r)));
                    float a = Mathf.Clamp01(r - Mathf.Sqrt(dx * dx + dy * dy) + 0.5f);
                    px[y * size + x] = new Color32(255, 255, 255, (byte)(a * 255));
                }
                tex.SetPixels32(px);
                tex.Apply();
                rounded = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100, 0,
                    SpriteMeshType.FullRect, new Vector4(r, r, r, r));
                return rounded;
            }
        }

        public static RectTransform Rect(Transform parent, string name, Vector2 anchorMin, Vector2 anchorMax,
            Vector2 offsetMin = default, Vector2 offsetMax = default)
        {
            var go = new GameObject(name, typeof(RectTransform));
            var rt = (RectTransform)go.transform;
            rt.SetParent(parent, false);
            rt.anchorMin = anchorMin;
            rt.anchorMax = anchorMax;
            rt.offsetMin = offsetMin;
            rt.offsetMax = offsetMax;
            return rt;
        }

        /// <summary>A rect placed by its top-left corner inside a parent that is anchored top-left.</summary>
        public static RectTransform Place(Transform parent, string name, float x, float y, float w, float h)
        {
            var rt = Rect(parent, name, new Vector2(0, 1), new Vector2(0, 1));
            rt.pivot = new Vector2(0, 1);
            rt.anchoredPosition = new Vector2(x, -y);
            rt.sizeDelta = new Vector2(w, h);
            return rt;
        }

        public static Image Panel(RectTransform rt, Color color, bool outline = true)
        {
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = Rounded;
            img.type = Image.Type.Sliced;
            img.color = color;
            if (outline)
            {
                var o = rt.gameObject.AddComponent<Outline>();
                o.effectColor = new Color(Ink.r, Ink.g, Ink.b, 0.55f);
                o.effectDistance = new Vector2(2, -2);
            }
            return img;
        }

        public static Text Label(Transform parent, string text, int size, Color color,
            TextAnchor align = TextAnchor.MiddleCenter, FontStyle style = FontStyle.Normal)
        {
            var rt = Rect(parent, "Text", Vector2.zero, Vector2.one, new Vector2(12, 6), new Vector2(-12, -6));
            var t = rt.gameObject.AddComponent<Text>();
            t.font = style == FontStyle.Bold ? FontBold : Font;
            t.text = text;
            t.fontSize = size;
            t.color = color;
            t.alignment = align;
            t.fontStyle = style == FontStyle.Bold ? FontStyle.Normal : style;   // real bold weight, not faked
            t.horizontalOverflow = HorizontalWrapMode.Wrap;
            t.verticalOverflow = VerticalWrapMode.Overflow;
            t.raycastTarget = false;
            return t;
        }

        public static Button Button(RectTransform rt, string text, int size, Color bg, Color fg,
            UnityEngine.Events.UnityAction onClick)
        {
            var img = Panel(rt, bg);
            var b = rt.gameObject.AddComponent<Button>();
            b.targetGraphic = img;
            var cb = b.colors;
            cb.highlightedColor = new Color(1.05f, 1.05f, 1.05f);
            cb.pressedColor = new Color(0.85f, 0.85f, 0.85f);
            b.colors = cb;
            if (!string.IsNullOrEmpty(text)) Label(rt, text, size, fg);
            if (onClick != null) b.onClick.AddListener(onClick);
            return b;
        }

        public static Canvas Canvas(string name, int order)
        {
            var go = new GameObject(name, typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var c = go.GetComponent<Canvas>();
            c.renderMode = RenderMode.ScreenSpaceOverlay;
            c.sortingOrder = order;
            var s = go.GetComponent<CanvasScaler>();
            s.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            s.referenceResolution = new Vector2(1920, 1080);
            s.matchWidthOrHeight = 0.5f;
            return c;
        }
    }
}
