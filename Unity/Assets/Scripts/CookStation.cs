using UnityEngine;
using UnityEngine.UI;

namespace BianHe
{
    /// <summary>
    /// Marks a prop as the way into the cooking screen (the 案台 in 初始·1桌). Adds a tap collider
    /// around the whole prop, a floating 「案台·做菜」 tag that bobs above it, and a soft pulsing
    /// highlight so a new player sees where to tap.
    /// </summary>
    public class CookStation : MonoBehaviour
    {
        public string tagText = "案台·做菜";
        public float tagHeight = 1.25f;

        Renderer[] renderers;
        MaterialPropertyBlock mpb;
        RectTransform tag;
        Text tagLabel;
        Image tagBg, tagTail;
        Vector3 tagBase;
        float flash;
        static readonly int HighlightId = Shader.PropertyToID("_Highlight");

        public void Setup(Camera cam)
        {
            renderers = GetComponentsInChildren<Renderer>();
            mpb = new MaterialPropertyBlock();

            var b = new Bounds(transform.position, Vector3.zero);
            foreach (var r in renderers) b.Encapsulate(r.bounds);
            var col = gameObject.AddComponent<BoxCollider>();
            col.center = transform.InverseTransformPoint(b.center);
            // the FBX nodes carry Blender's axis rotation, so bring the world size into local axes
            var local = transform.InverseTransformVector(b.size + new Vector3(0.3f, 0.3f, 0.3f));   // a little extra so fingers find it
            col.size = new Vector3(Mathf.Abs(local.x), Mathf.Abs(local.y), Mathf.Abs(local.z));

            // floating tag, a world-space canvas that always faces the camera
            var canvasGo = new GameObject("StationTag", typeof(Canvas));
            var canvas = canvasGo.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            canvas.worldCamera = cam;
            tag = (RectTransform)canvasGo.transform;
            tag.SetParent(transform, false);   // world-space placement below, whatever the node's axes
            tag.sizeDelta = new Vector2(360, 110);
            tag.localScale = Vector3.one * 0.0042f;
            tagBase = new Vector3(b.center.x, b.max.y + tagHeight * 0.5f, b.center.z);
            tag.position = tagBase;
            var bg = UIKit.Rect(tag, "Bg", Vector2.zero, Vector2.one);
            tagBg = UIKit.Panel(bg, UIKit.Paper);
            tagLabel = UIKit.Label(bg, tagText, 54, UIKit.Ink, TextAnchor.MiddleCenter, FontStyle.Bold);
            var tail = UIKit.Rect(tag, "Tail", new Vector2(0.5f, 0), new Vector2(0.5f, 0));
            tail.sizeDelta = new Vector2(28, 28);
            tail.anchoredPosition = new Vector2(0, -6);
            tail.localRotation = Quaternion.Euler(0, 0, 45);
            tagTail = tail.gameObject.AddComponent<Image>();
            tagTail.color = UIKit.Paper;
            tail.SetAsFirstSibling();
        }

        public void Flash() => flash = 1f;

        /// <summary>Switch the tag between its normal text and an alert (e.g. a dish waiting to 出炉).</summary>
        public void SetAlert(string alert)
        {
            if (!tagLabel) return;
            tagLabel.text = alert ?? tagText;
            var bg = alert == null ? UIKit.Paper : UIKit.Good;
            tagBg.color = tagTail.color = bg;
            tagLabel.color = alert == null ? UIKit.Ink : Color.white;
        }

        public void ShowTag(bool on)
        {
            if (tag) tag.gameObject.SetActive(on);
        }

        void LateUpdate()
        {
            var cam = Camera.main;
            if (tag && cam)
            {
                tag.rotation = cam.transform.rotation;
                // keep the tag a readable size on screen whatever the zoom
                float s = 0.0042f * Mathf.Clamp(cam.orthographicSize / 4f, 0.6f, 1.6f);
                tag.localScale = Vector3.one * s;
                tag.position = tagBase + Vector3.up * (Mathf.Sin(Time.time * 2.4f) * 0.06f);
            }
            flash = Mathf.Max(0, flash - Time.deltaTime * 3f);
            float pulse = 0.12f + 0.12f * Mathf.Sin(Time.time * 3f);
            mpb.SetFloat(HighlightId, Mathf.Max(pulse, flash));
            foreach (var r in renderers) r.SetPropertyBlock(mpb);
        }
    }
}
