// 三渲二 toon shader for 汴河两岸, the Unity counterpart of the 纹璃宫灯 Blender preview:
// two flat tones (lit / shade) split by the main light, hard-edged received shadows, and an
// inverted-hull outline. The outline pushes along the smoothed normal the model importer stores in
// UV3 (Level1ModelPostprocessor), so the hull stays closed across the hardened bevel normals.
Shader "BianHe/ToonLit"
{
    Properties
    {
        _BaseColor ("Lit Color", Color) = (0.86, 0.64, 0.36, 1)
        _ShadeColor ("Shade Color", Color) = (0.70, 0.48, 0.23, 1)
        _Threshold ("Light Threshold", Range(-1, 1)) = 0.0
        _Softness ("Edge Softness", Range(0.001, 0.3)) = 0.02
        _ShadowStrength ("Received Shadow", Range(0, 1)) = 0.85
        _Emission ("Self Lit", Range(0, 1)) = 0
        _OutlineColor ("Outline Color", Color) = (0.35, 0.23, 0.15, 1)
        _OutlineWidth ("Outline Width (px @1080p)", Range(0, 6)) = 2.2
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
            half _Threshold;
            half _Softness;
            half _ShadowStrength;
            half _Emission;
            half4 _OutlineColor;
            float _OutlineWidth;
            half _Highlight;
        CBUFFER_END

        // Set by CameraRig: lines thicken a little as the player zooms in.
        float _ToonOutlineScale;
        ENDHLSL

        Pass
        {
            Name "ToonForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                half fog : TEXCOORD2;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                VertexPositionInputs p = GetVertexPositionInputs(v.positionOS.xyz);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.fog = ComputeFogFactor(p.positionCS.z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                Light light = GetMainLight(TransformWorldToShadowCoord(i.positionWS));
                half ndl = dot(normalize(i.normalWS), light.direction);
                half lit = smoothstep(_Threshold - _Softness, _Threshold + _Softness, ndl);
                half shadow = smoothstep(0.35, 0.65, light.shadowAttenuation);
                lit *= lerp(1.0h, shadow, _ShadowStrength);
                lit = max(lit, _Emission);
                half3 col = lerp(_ShadeColor.rgb, _BaseColor.rgb, lit);
                col += _Emission * 0.12h;
                col = lerp(col, col * 1.25h + 0.08h, _Highlight);
                col = MixFog(col, i.fog);
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
                float3 nWS = TransformObjectToWorldNormal(n);
                float2 nCS = mul((float3x3)UNITY_MATRIX_VP, nWS).xy;
                float len = length(nCS);
                if (len > 1e-4)
                {
                    float scale = _ToonOutlineScale > 0 ? _ToonOutlineScale : 1.0;
                    float px = _OutlineWidth * scale * (_ScreenParams.y / 1080.0);
                    cs.xy += (nCS / len) * px * 2.0 / _ScreenParams.xy * cs.w;
                }
                // nudge the hull back so it never covers its own front faces at grazing angles
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

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On ZTest LEqual ColorMask 0 Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            float3 _LightDirection;
            float3 _LightPosition;

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; };

            float4 vert(Attributes v) : SV_POSITION
            {
                float3 posWS = TransformObjectToWorld(v.positionOS.xyz);
                float3 nWS = TransformObjectToWorldNormal(v.normalOS);
                #if _CASTING_PUNCTUAL_LIGHT_SHADOW
                    float3 lightDir = normalize(_LightPosition - posWS);
                #else
                    float3 lightDir = _LightDirection;
                #endif
                float4 cs = TransformWorldToHClip(ApplyShadowBias(posWS, nWS, lightDir));
                #if UNITY_REVERSED_Z
                    cs.z = min(cs.z, UNITY_NEAR_CLIP_VALUE);
                #else
                    cs.z = max(cs.z, UNITY_NEAR_CLIP_VALUE);
                #endif
                return cs;
            }

            half4 frag() : SV_Target { return 0; }
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On ColorMask R Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            struct Attributes { float4 positionOS : POSITION; };
            float4 vert(Attributes v) : SV_POSITION { return TransformObjectToHClip(v.positionOS.xyz); }
            half frag() : SV_Target { return 0; }
            ENDHLSL
        }
    }
}
