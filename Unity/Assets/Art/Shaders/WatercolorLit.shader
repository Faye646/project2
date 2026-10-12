// 水彩 look for 汴河两岸 (the teacher-approved style C), the real-time counterpart of
// WhiteModel/wc_materials.py: a patch of the painted art projected on the model (triplanar, object
// space, mirrored), soft 4-step light with cooler, darker shadows and a warm top light, cartoon cast
// shadows on the ground things stand on (flat, clean-edged), pigment pooling in crevices (SSAO when the renderer has it, plus low-in-the-room
// darkening), dappled leaf light on walls and floors, paper grain in screen space, and a warm ink
// outline (inverted hull, same smooth normals as ToonLit). Food also gets fuller colour with deep,
// saturated shadows (_Vivid) and a painted gloss: a sheen and a small bright glint where it mirrors the
// light (_Gloss), as in the dish art. Meat also gets a painted surface: a tileable detail texture box-projected
// in object space (the food has no UVs) whose pattern tints the colour (_DetailAmount toward _DetailColor) and
// whose height bumps the normals for the light steps and the gloss (_BumpAmount, relief in mm), skipped by a
// branch on the material unless one of the two is above 0. Fish and crab are painted across their surface too:
// each vertex carries a colour the material's own leans toward (_VertexTint), by 1 - its alpha, so that the dark
// crown of a fish head fades into its pale cheek and a crab's legs warm to orange at the joints; a mesh without
// vertex colours reads white, alpha 1, and is left as it is.
Shader "BianHe/WatercolorLit"
{
    Properties
    {
        _BaseColor ("Lit Color", Color) = (0.95, 0.88, 0.7, 1)
        _ShadeColor ("Shade Color", Color) = (0.85, 0.75, 0.55, 1)
        [NoScaleOffset] _PaintTex ("Painted Patch", 2D) = "white" {}
        _UsePaint ("Use Painted Patch", Range(0, 1)) = 0
        _PaintScale ("Patch Scale (per metre)", Float) = 1
        _Saturation ("Saturation", Float) = 1.28
        _Value ("Value", Float) = 1.08
        [NoScaleOffset] _NoiseTex ("Noise (R broad, G mid, B fine)", 2D) = "gray" {}
        _Dappled ("Dappled Light", Range(0, 1)) = 0
        _Emission ("Self Lit", Range(0, 1)) = 0
        _OutlineColor ("Outline Color", Color) = (0.42, 0.27, 0.19, 1)
        _OutlineWidth ("Outline Width (px @1080p)", Range(0, 6)) = 1.6
        _Highlight ("Highlight", Range(0, 1)) = 0
        _Vivid ("Rich Colour (food)", Range(0, 1)) = 0
        _Gloss ("Gloss", Range(0, 1)) = 0
        [NoScaleOffset] _DetailTex ("Detail (R pattern, G height), tiling", 2D) = "black" {}
        _DetailScale ("Detail Tiles per Metre", Float) = 20
        _DetailColor ("Detail Color", Color) = (1, 1, 1, 1)
        _DetailAmount ("Detail Tint", Range(0, 1)) = 0
        _BumpAmount ("Bump (relief, mm)", Range(0, 3)) = 0
        _VertexTint ("Painted Tint (vertex colours)", Range(0, 1)) = 0
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" "Queue" = "Geometry" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            half4 _BaseColor;
            half4 _ShadeColor;
            half _UsePaint;
            float _PaintScale;
            half _Saturation;
            half _Value;
            half _Dappled;
            half _Emission;
            half4 _OutlineColor;
            float _OutlineWidth;
            half _Highlight;
            half _Vivid;
            half _Gloss;
            float _DetailScale;
            half4 _DetailColor;
            half _DetailAmount;
            half _BumpAmount;
            half _VertexTint;
        CBUFFER_END
        float _ToonOutlineScale;
        // where the painted light comes from (ShadeLight on the sun sets it, w = 1): the light steps, the wash and the
        // glints follow it, while the shadows are cast from the sun's own direction, steeper and from the side, so
        // that they fall where the camera sees them (a light from behind the camera hides every shadow behind the
        // thing casting it). w = 0: the sun does both.
        float4 _ShadeLightDir;
        ENDHLSL

        Pass
        {
            Name "WatercolorForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            TEXTURE2D(_PaintTex); SAMPLER(sampler_PaintTex);
            TEXTURE2D(_NoiseTex); SAMPLER(sampler_NoiseTex);
            TEXTURE2D(_DetailTex); SAMPLER(sampler_DetailTex);

            struct Attributes
            {
                float4 positionOS : POSITION; float3 normalOS : NORMAL; float3 smoothNormal : TEXCOORD3; half4 color : COLOR;
            };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 positionOS : TEXCOORD2;
                float3 normalOS : TEXCOORD3;
                float4 screenPos : TEXCOORD4;
                float3 glossNormalWS : TEXCOORD5;   // the smoothed normal: glints run round a low-poly shape
                half4 color : TEXCOORD6;            // the painted tint: a colour, and 1 - how far toward it
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                VertexPositionInputs p = GetVertexPositionInputs(v.positionOS.xyz);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.positionOS = v.positionOS.xyz;
                o.normalOS = v.normalOS;
                o.screenPos = ComputeScreenPos(p.positionCS);
                o.glossNormalWS = TransformObjectToWorldNormal(dot(v.smoothNormal, v.smoothNormal) > 0.01 ? v.smoothNormal : v.normalOS);
                o.color = v.color;
                return o;
            }

            half3 Saturate3(half3 c, half s, half v)
            {
                half l = dot(c, half3(0.3, 0.59, 0.11));
                return max(0, lerp(l.xxx, c, s)) * v;
            }

            // food colour as rich as the dish art: saturation raised along 1 - (1 - s)^k (pale colours gain
            // most, strong ones ease toward full instead of clipping), same hue and value, then the
            // saturated ones deepened a little
            half3 Vibrant(half3 c, half k, half deepen)
            {
                half mx = max(c.r, max(c.g, c.b));
                half mn = min(c.r, min(c.g, c.b));
                if (mx - mn < 1e-4) return c;
                half s = (mx - mn) / mx;
                half s2 = 1 - pow(1 - s, k);
                half3 hue = (c - mn) / (mx - mn);
                return mx * (1 - s2 * (1 - hue)) * (1 - deepen * s2);
            }

            // box projection of the painted patch, like Blender's BOX projection with mirror repeat
            half3 Triplanar(float3 p, float3 n)
            {
                float3 w = pow(abs(n), 6);
                w /= (w.x + w.y + w.z);
                p *= _PaintScale;
                half3 x = SAMPLE_TEXTURE2D(_PaintTex, sampler_PaintTex, p.zy).rgb;
                half3 y = SAMPLE_TEXTURE2D(_PaintTex, sampler_PaintTex, p.xz).rgb;
                half3 z = SAMPLE_TEXTURE2D(_PaintTex, sampler_PaintTex, p.xy).rgb;
                return x * w.x + y * w.y + z * w.z;
            }

            // the meat's detail texture (R pattern, G height), box-projected and repeated, _DetailScale tiles a
            // metre. Gradients come in from outside the branch it is called in (dp = ddx/ddy of the position).
            float2 TriplanarDetail(float3 p, float3 n, float3 dpx, float3 dpy)
            {
                float3 w = pow(abs(n), 6);
                w /= (w.x + w.y + w.z);
                p *= _DetailScale; dpx *= _DetailScale; dpy *= _DetailScale;
                float2 x = SAMPLE_TEXTURE2D_GRAD(_DetailTex, sampler_DetailTex, p.zy, dpx.zy, dpy.zy).rg;
                float2 y = SAMPLE_TEXTURE2D_GRAD(_DetailTex, sampler_DetailTex, p.xz, dpx.xz, dpy.xz).rg;
                float2 z = SAMPLE_TEXTURE2D_GRAD(_DetailTex, sampler_DetailTex, p.xy, dpx.xy, dpy.xy).rg;
                return x * w.x + y * w.y + z * w.z;
            }

            // normalize(|det|·n − grad), the bumped normal of Mikkelsen 2010; n itself where that vanishes
            float3 Bumped(float3 n, float3 grad, float det)
            {
                float3 b = abs(det) * n - grad;
                float l = dot(b, b);
                return l > 1e-30 ? b * rsqrt(l) : n;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float3 n = normalize(i.normalWS);
                float3 n0 = n;                                  // the unbumped normal, for the pooling
                float3 glossN = normalize(i.glossNormalWS);
                half3 noise = SAMPLE_TEXTURE2D(_NoiseTex, sampler_NoiseTex, i.positionWS.xz * 0.12 + i.positionWS.y * 0.05).rgb;

                // base: flat colour broken by stains, or the painted patch
                half3 flat = lerp(_BaseColor.rgb, lerp(_BaseColor.rgb, _ShadeColor.rgb, 0.45), smoothstep(0.45, 0.75, noise.g));
                flat = lerp(flat, i.color.rgb, (1 - i.color.a) * _VertexTint);   // painted across the surface (linear)
                flat = lerp(flat, Vibrant(flat, 1.9, 0.15), _Vivid);   // food: the full colour of the dish art
                half3 paint = Saturate3(Triplanar(i.positionOS, normalize(i.normalOS)), _Saturation, _Value);
                half3 base = lerp(flat, paint, _UsePaint);

                // meat: the detail pattern tints the colour, its height bumps both normals (Mikkelsen 2010, bump
                // mapping unparametrized surfaces: screen-space derivatives of the position and the height). The
                // derivatives stay outside the branches; the position's are taken in object space and turned to
                // world space, the same vectors as ddx/ddy(positionWS) but exact far from the origin (the cook set).
                float3 dpx = ddx(i.positionOS), dpy = ddy(i.positionOS);
                float2 detail = 0;
                bool hasDetail = _DetailAmount + _BumpAmount > 0;
                UNITY_BRANCH
                if (hasDetail) detail = TriplanarDetail(i.positionOS, normalize(i.normalOS), dpx, dpy);
                float dhdx = ddx(detail.y), dhdy = ddy(detail.y);
                UNITY_BRANCH
                if (hasDetail)
                {
                    base = lerp(base, _DetailColor.rgb, detail.x * _DetailAmount);
                    float3x3 m = (float3x3)GetObjectToWorldMatrix();
                    float3 sx = mul(m, dpx), sy = mul(m, dpy);
                    float3 r1 = cross(sy, n), r2 = cross(n, sx);
                    float det = dot(sx, r1);
                    float3 grad = sign(det) * (dhdx * r1 + dhdy * r2) * (_BumpAmount * 0.001);   // height in metres
                    // no steeper than 45° (grazing views, where det runs to 0)
                    float g2 = dot(grad, grad);
                    if (g2 > det * det) grad *= abs(det) * rsqrt(g2);
                    n = Bumped(n, grad, det);
                    glossN = Bumped(glossN, grad * 0.5, det);   // half as much: glints break into dabs, not grit
                }

                if (_Emission > 0.5) return half4(base, 1);

                // light: diffuse, painted into 4 soft steps. The cast shadows come after, as a cartoon's: where the
                // sun (high above) is hidden, with a clean edge (the shadow map's soft edge narrowed to a line), only
                // on what faces up to it (floors, seats, table tops, the stove top: the ground things stand on), never
                // on a wall or a face turned from it, which the shadow map darkens though the painted light lights it
                Light light = GetMainLight(TransformWorldToShadowCoord(i.positionWS));
                float3 L = _ShadeLightDir.w > 0.5 ? normalize(_ShadeLightDir.xyz) : light.direction;
                half cast = saturate((1 - light.shadowAttenuation) / max(GetMainLightShadowParams().x, 1e-3));
                cast = smoothstep(0.35, 0.6, cast) * smoothstep(0.3, 0.5, dot(n0, light.direction));
                half d = saturate(dot(n, L));
                half ambient = 0.25;
                half lum = ambient + d * 0.75;
                half steps = smoothstep(0.25, 0.42, lum) * 0.45 + smoothstep(0.42, 0.62, lum) * 0.37 + smoothstep(0.62, 0.9, lum) * 0.18;
                half3 cool = half3(0.34, 0.36, 0.55);
                half3 shadowCol = lerp(base * 0.54, cool, 0.2);
                shadowCol = lerp(shadowCol, Vibrant(base * 0.58, 1.4, 0.0), _Vivid);   // food: deep shadows, not grey ones
                half3 col = lerp(shadowCol, base, steps);
                half hi = saturate((steps - 0.85) * 5.0);
                // the warm top light washes the lit side toward warm white; what is painted across its surface (fish,
                // crab) only warms and brightens a little there, so that its dark paint stays dark in the light
                half3 wash = lerp(lerp(base, half3(1.0, 0.86, 0.62), 0.35), base * half3(1.15, 1.07, 0.97), _VertexTint);
                col = lerp(col, wash, hi * 0.6 * (1 - 0.6 * _Vivid));

                // gloss: a sheen where the surface mirrors the light, and at its heart a small bright glint, a dab
                // of white as in the dish art, its edge broken a little like a brush stroke. a, the distance from
                // the normal to the half vector, is about the angle between them in radians.
                float3 h = normalize(L + GetWorldSpaceNormalizeViewDir(i.positionWS));
                float a = distance(glossN, h);
                half sheen = (1 - smoothstep(0.25, 0.6, a)) * (1 - cast);
                half glint = (1 - smoothstep(0.1, 0.16, a * (1 + (noise.b - 0.5) * 0.3))) * (1 - cast);
                col = lerp(col, col * 1.12 + 0.04, sheen * _Gloss * 0.5);
                col = lerp(col, half3(1.0, 0.98, 0.92), glint * _Gloss * 0.85);

                // the cast shadow: one flat colour, well under half as bright as the paint and cooler (food: its own colour,
                // deep), never lighter than the shade already there
                half3 castCol = lerp(base * half3(0.42, 0.4, 0.54), Vibrant(base * 0.5, 1.4, 0.0), _Vivid);
                col = lerp(col, min(col, castCol), cast);

                // pigment pooling: SSAO if present, and a little toward the floor
                half occl = 0;
                #if defined(_SCREEN_SPACE_OCCLUSION)
                    float2 suv = i.screenPos.xy / i.screenPos.w;
                    occl = 1 - SampleAmbientOcclusion(suv);
                #endif
                occl = max(occl, saturate(0.6 - i.positionWS.y * 0.9) * 0.35 * saturate(1 - abs(n0.y)));
                col = lerp(col, half3(0.36, 0.2, 0.11), occl * 0.55);

                // dappled leaf light on lit walls and floors
                half spots = smoothstep(0.52, 0.6, noise.r) * steps;
                half dapple = _Dappled * (1 - cast);   // none in a cast shadow: it stays one flat colour
                col = lerp(col, lerp(base, half3(1.0, 0.86, 0.62), 0.45), spots * 0.35 * dapple);
                col = lerp(col, lerp(base, cool, 0.12), (1 - smoothstep(0.52, 0.6, noise.r)) * 0.18 * dapple);

                // paper grain, fixed to the screen
                float2 grainUV = i.screenPos.xy / i.screenPos.w * _ScreenParams.xy / 256.0;
                half grain = SAMPLE_TEXTURE2D(_NoiseTex, sampler_NoiseTex, grainUV).b;
                col *= 0.955 + 0.07 * grain;

                col = lerp(col, col * 1.25h + 0.08h, _Highlight);
                return half4(col, 1);
            }
            ENDHLSL
        }

        Pass
        {
            Name "Outline"
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Cull Front

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; float3 smoothNormal : TEXCOORD3; };
            struct Varyings { float4 positionCS : SV_POSITION; };

            Varyings vert(Attributes v)
            {
                Varyings o;
                float3 n = dot(v.smoothNormal, v.smoothNormal) > 0.01 ? v.smoothNormal : v.normalOS;
                float4 cs = TransformObjectToHClip(v.positionOS.xyz);
                float2 nCS = mul((float3x3)UNITY_MATRIX_VP, TransformObjectToWorldNormal(n)).xy;
                float len = length(nCS);
                if (len > 1e-4)
                {
                    float scale = _ToonOutlineScale > 0 ? _ToonOutlineScale : 1.0;
                    cs.xy += (nCS / len) * _OutlineWidth * scale * (_ScreenParams.y / 1080.0) * 2.0 / _ScreenParams.xy * cs.w;
                }
                #if UNITY_REVERSED_Z
                    cs.z -= 0.0002 * cs.w;
                #else
                    cs.z += 0.0002 * cs.w;
                #endif
                o.positionCS = cs;
                return o;
            }
            half4 frag(Varyings i) : SV_Target { return half4(_OutlineColor.rgb, 1); }
            ENDHLSL
        }

        UsePass "BianHe/ToonLit/ShadowCaster"
        UsePass "BianHe/ToonLit/DepthOnly"

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On Cull Back
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; };
            struct Varyings { float4 positionCS : SV_POSITION; float3 normalWS : TEXCOORD0; };
            Varyings vert(Attributes v)
            {
                Varyings o;
                o.positionCS = TransformObjectToHClip(v.positionOS.xyz);
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                return o;
            }
            half4 frag(Varyings i) : SV_Target { return half4(normalize(i.normalWS), 0); }
            ENDHLSL
        }
    }
}
