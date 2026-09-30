// 水彩 look for 汴河两岸 (the teacher-approved style C), the real-time counterpart of
// WhiteModel/wc_materials.py: a patch of the painted art projected on the model (triplanar, object
// space, mirrored), soft 4-step light with cooler, darker shadows and a warm top light, received
// shadows, pigment pooling in crevices (SSAO when the renderer has it, plus low-in-the-room
// darkening), dappled leaf light on walls and floors, paper grain in screen space, and a warm ink
// outline (inverted hull, same smooth normals as ToonLit).
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
        CBUFFER_END
        float _ToonOutlineScale;
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

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 positionOS : TEXCOORD2;
                float3 normalOS : TEXCOORD3;
                float4 screenPos : TEXCOORD4;
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
                return o;
            }

            half3 Saturate3(half3 c, half s, half v)
            {
                half l = dot(c, half3(0.3, 0.59, 0.11));
                return max(0, lerp(l.xxx, c, s)) * v;
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

            half4 frag(Varyings i) : SV_Target
            {
                float3 n = normalize(i.normalWS);
                half3 noise = SAMPLE_TEXTURE2D(_NoiseTex, sampler_NoiseTex, i.positionWS.xz * 0.12 + i.positionWS.y * 0.05).rgb;

                // base: flat colour broken by stains, or the painted patch
                half3 flat = lerp(_BaseColor.rgb, lerp(_BaseColor.rgb, _ShadeColor.rgb, 0.45), smoothstep(0.45, 0.75, noise.g));
                half3 paint = Saturate3(Triplanar(i.positionOS, normalize(i.normalOS)), _Saturation, _Value);
                half3 base = lerp(flat, paint, _UsePaint);
                if (_Emission > 0.5) return half4(base, 1);

                // light: diffuse × shadow, painted into 4 soft steps
                Light light = GetMainLight(TransformWorldToShadowCoord(i.positionWS));
                half d = saturate(dot(n, light.direction)) * light.shadowAttenuation;
                half ambient = 0.25;
                half lum = ambient + d * 0.75;
                half steps = smoothstep(0.25, 0.42, lum) * 0.45 + smoothstep(0.42, 0.62, lum) * 0.37 + smoothstep(0.62, 0.9, lum) * 0.18;
                half3 cool = half3(0.34, 0.36, 0.55);
                half3 shadowCol = lerp(base * 0.54, cool, 0.2);
                half3 col = lerp(shadowCol, base, steps);
                half hi = saturate((steps - 0.85) * 5.0);
                col = lerp(col, lerp(base, half3(1.0, 0.86, 0.62), 0.35), hi * 0.6);

                // pigment pooling: SSAO if present, and a little toward the floor
                half occl = 0;
                #if defined(_SCREEN_SPACE_OCCLUSION)
                    float2 suv = i.screenPos.xy / i.screenPos.w;
                    occl = 1 - SampleAmbientOcclusion(suv);
                #endif
                occl = max(occl, saturate(0.6 - i.positionWS.y * 0.9) * 0.35 * saturate(1 - abs(n.y)));
                col = lerp(col, half3(0.36, 0.2, 0.11), occl * 0.55);

                // dappled leaf light on lit walls and floors
                half spots = smoothstep(0.52, 0.6, noise.r) * steps;
                col = lerp(col, lerp(base, half3(1.0, 0.86, 0.62), 0.45), spots * 0.35 * _Dappled);
                col = lerp(col, lerp(base, cool, 0.12), (1 - smoothstep(0.52, 0.6, noise.r)) * 0.18 * _Dappled);

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
