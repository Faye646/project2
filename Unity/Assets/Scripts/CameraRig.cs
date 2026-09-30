using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.EnhancedTouch;
using Touch = UnityEngine.InputSystem.EnhancedTouch.Touch;

namespace BianHe
{
    /// <summary>
    /// Fixed-angle orthographic camera for the shop floor (2:1 isometric, like the level art).
    /// Phone: one finger drags the view, two fingers pinch to zoom around the pinch point, a short tap
    /// selects. Editor / PC: left or right mouse drag, scroll wheel zoom at the cursor, click to select.
    /// The view is clamped so the shop never leaves the screen.
    /// </summary>
    [RequireComponent(typeof(Camera))]
    public class CameraRig : MonoBehaviour
    {
        [Header("View")]
        public float yaw = 45f;
        public float pitch = 30f;
        public float distance = 60f;
        public float groundHeight = 0.45f;

        [Header("Zoom (orthographic size)")]
        public float minSize = 2.2f;
        public float maxSize = 8f;
        public float wheelStep = 0.12f;

        [Header("Bounds of the pivot on the ground (world XZ)")]
        public Rect bounds = new Rect(-10, -10, 20, 20);

        [Header("Feel")]
        public float tapMaxMove = 12f;     // pixels at 160 dpi
        public float tapMaxTime = 0.35f;
        public float inertiaDamping = 6f;

        public event Action<Vector2> Tapped;   // screen position of a tap that wasn't a drag
        public bool InputEnabled { get; set; } = true;

        Camera cam;
        Vector3 pivot;
        Vector3 velocity;
        Plane ground;

        // pointer bookkeeping
        bool pointerDown, dragging, pinching, overUI;
        Vector2 downPos, lastPos;
        float downTime;
        float lastPinchDist;
        Vector2 lastPinchMid;

        static readonly int OutlineScaleId = Shader.PropertyToID("_ToonOutlineScale");

        public Camera Cam => cam;
        float DpiScale => Mathf.Max(1f, (Screen.dpi > 0 ? Screen.dpi : 160f) / 160f);

        void Awake()
        {
            cam = GetComponent<Camera>();
            cam.orthographic = true;
            ground = new Plane(Vector3.up, new Vector3(0, groundHeight, 0));
        }

        void OnEnable() => EnhancedTouchSupport.Enable();
        void OnDisable() => EnhancedTouchSupport.Disable();

        /// <summary>Frames the whole shop: pivot at the centre of the bounds, zoomed out to fit.</summary>
        public void Frame(Vector3 center, float size)
        {
            pivot = new Vector3(center.x, groundHeight, center.z);
            cam.orthographicSize = Mathf.Clamp(size, minSize, maxSize);
            velocity = Vector3.zero;
            Apply();
        }

        void Update()
        {
            if (InputEnabled)
            {
                if (Touch.activeTouches.Count > 0) HandleTouches();
                else HandleMouse();
            }
            else
            {
                pointerDown = dragging = pinching = false;
            }

            if (!pointerDown && velocity.sqrMagnitude > 1e-6f)
            {
                pivot += velocity * Time.unscaledDeltaTime;
                velocity = Vector3.Lerp(velocity, Vector3.zero, 1 - Mathf.Exp(-inertiaDamping * Time.unscaledDeltaTime));
            }
            Apply();
        }

        // ------------------------------------------------------------------ touch

        void HandleTouches()
        {
            var touches = Touch.activeTouches;
            if (touches.Count >= 2)
            {
                Vector2 a = touches[0].screenPosition, b = touches[1].screenPosition;
                float dist = Vector2.Distance(a, b);
                Vector2 mid = (a + b) * 0.5f;
                if (!pinching)
                {
                    pinching = true;
                    dragging = true;     // a pinch never counts as a tap
                    lastPinchDist = dist;
                    lastPinchMid = mid;
                    velocity = Vector3.zero;
                    return;
                }
                if (dist > 1f && lastPinchDist > 1f) ZoomAt(mid, lastPinchDist / dist);
                PanBetween(lastPinchMid, mid, false);
                lastPinchDist = dist;
                lastPinchMid = mid;
                return;
            }

            var t = touches[0];
            if (pinching)
            {
                // one finger lifted after a pinch: continue as a drag from here without jumping
                pinching = false;
                lastPos = t.screenPosition;
                return;
            }
            switch (t.phase)
            {
                case UnityEngine.InputSystem.TouchPhase.Began:
                    PointerDown(t.screenPosition, IsOverUI(t.touchId));
                    break;
                case UnityEngine.InputSystem.TouchPhase.Moved:
                case UnityEngine.InputSystem.TouchPhase.Stationary:
                    PointerMove(t.screenPosition);
                    break;
                case UnityEngine.InputSystem.TouchPhase.Ended:
                case UnityEngine.InputSystem.TouchPhase.Canceled:
                    PointerUp(t.screenPosition);
                    break;
            }
        }

        // ------------------------------------------------------------------ mouse

        void HandleMouse()
        {
            var m = Mouse.current;
            if (m == null) return;
            Vector2 pos = m.position.ReadValue();
            bool pressed = m.leftButton.isPressed || m.rightButton.isPressed || m.middleButton.isPressed;
            if (pressed && !pointerDown) PointerDown(pos, IsOverUI(-1));
            else if (pressed) PointerMove(pos);
            else if (pointerDown) PointerUp(pos);

            float scroll = m.scroll.ReadValue().y;
            if (Mathf.Abs(scroll) > 0.01f && !IsOverUI(-1))
                ZoomAt(pos, Mathf.Pow(1 + wheelStep, -Mathf.Sign(scroll)));
        }

        // ------------------------------------------------------------------ shared pointer logic

        void PointerDown(Vector2 pos, bool uiHit)
        {
            pointerDown = true;
            dragging = false;
            overUI = uiHit;
            downPos = lastPos = pos;
            downTime = Time.unscaledTime;
            velocity = Vector3.zero;
        }

        void PointerMove(Vector2 pos)
        {
            if (!pointerDown || overUI) return;
            if (!dragging && (pos - downPos).magnitude > tapMaxMove * DpiScale) dragging = true;
            if (dragging) PanBetween(lastPos, pos, true);
            lastPos = pos;
        }

        void PointerUp(Vector2 pos)
        {
            if (pointerDown && !overUI && !dragging && Time.unscaledTime - downTime <= tapMaxTime)
                Tapped?.Invoke(pos);
            pointerDown = dragging = false;
        }

        bool IsOverUI(int pointerId)
        {
            var es = EventSystem.current;
            if (es == null) return false;
            return pointerId >= 0 ? es.IsPointerOverGameObject(pointerId) : es.IsPointerOverGameObject();
        }

        // ------------------------------------------------------------------ camera math

        bool GroundPoint(Vector2 screen, out Vector3 p)
        {
            var ray = cam.ScreenPointToRay(screen);
            if (ground.Raycast(ray, out float d)) { p = ray.GetPoint(d); return true; }
            p = default;
            return false;
        }

        void PanBetween(Vector2 from, Vector2 to, bool track)
        {
            if (!GroundPoint(from, out var a) || !GroundPoint(to, out var b)) return;
            var delta = a - b;
            pivot += delta;
            if (track && Time.unscaledDeltaTime > 0)
                velocity = Vector3.Lerp(velocity, delta / Time.unscaledDeltaTime, 0.5f);
            Apply();
        }

        void ZoomAt(Vector2 screen, float factor)
        {
            GroundPoint(screen, out var before);
            cam.orthographicSize = Mathf.Clamp(cam.orthographicSize * factor, minSize, maxSize);
            Apply();
            if (GroundPoint(screen, out var after)) pivot += before - after;
            Apply();
        }

        void Apply()
        {
            pivot.x = Mathf.Clamp(pivot.x, bounds.xMin, bounds.xMax);
            pivot.z = Mathf.Clamp(pivot.z, bounds.yMin, bounds.yMax);
            pivot.y = groundHeight;
            var rot = Quaternion.Euler(pitch, yaw, 0);
            transform.SetPositionAndRotation(pivot - rot * Vector3.forward * distance, rot);
            Shader.SetGlobalFloat(OutlineScaleId, Mathf.Clamp(Mathf.Sqrt(maxSize / cam.orthographicSize) * 0.85f, 0.9f, 1.8f));
        }
    }
}
