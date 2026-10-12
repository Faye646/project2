// What the shop can buy next, standing where it will go as a see-through sketch (ShopFloor): pale paper washed with
// the blue of the door curtains, lighter on its tops, faintly hatched like a builder's plan, a blue ink line round its
// silhouette, and breathing slowly so that it reads as "for sale" rather than as furniture. Only its nearest surface
// shows: a depth pass first (SRPDefaultUnlit, drawn before UniversalForward), so the legs behind a table top don't pile
// up. It lives in Resources so that the player includes it (ShopFloor loads it by name).
Shader "BianHe/Ghost"
{
    Properties
    {
        _Wash ("Wash", Color) = (0.365, 0.533, 0.714, 1)
        _Paper ("Paper", Color) = (0.97, 0.94, 0.86, 1)
        _Ink ("Ink", Color) = (0.22, 0.36, 0.55, 1)
        _Alpha ("Opacity", Range(0, 1)) = 0.5
        _Breath ("Breathing", Range(0, 0.5)) = 0.14
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            half4 _Wash;
            half4 _Paper;
            half4 _Ink;
            half _Alpha;
            half _Breath;
        CBUFFER_END
        ENDHLSL

        Pass
        {
            Name "SketchDepth"
            Tags { "LightMode" = "SRPDefaultUnlit" }
            ZWrite On
            ColorMask 0
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            float4 vert(float4 positionOS : POSITION) : SV_POSITION { return TransformObjectToHClip(positionOS.xyz); }
            half4 frag() : SV_Target { return 0; }
            ENDHLSL
        }

        Pass
        {
            Name "SketchForward"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite Off
            ZTest LEqual
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; float3 smoothNormal : TEXCOORD3; };
            struct Varyings { float4 positionCS : SV_POSITION; float3 positionWS : TEXCOORD0; float3 normalWS : TEXCOORD1; };

            Varyings vert(Attributes v)
            {
                Varyings o;
                VertexPositionInputs p = GetVertexPositionInputs(v.positionOS.xyz);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                // the smooth normals the importer bakes for the ink outline (UV3) round the silhouette off
                o.normalWS = TransformObjectToWorldNormal(dot(v.smoothNormal, v.smoothNormal) > 0.01 ? v.smoothNormal : v.normalOS);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float3 n = normalize(i.normalWS);
                float3 v = GetWorldSpaceNormalizeViewDir(i.positionWS);
                half nv = saturate(abs(dot(n, v)));
                // paper on the tops, more of the blue down the sides
                half3 col = lerp(_Wash.rgb, _Paper.rgb, 0.35 + 0.45 * saturate(n.y));
                // a builder's plan: thin diagonal hatching in screen space, about 9 px apart at 1080p
                float2 px = i.positionCS.xy * (1080.0 / _ScreenParams.y);
                half hatch = smoothstep(0.75, 0.95, frac((px.x + px.y) / 9.0));
                col = lerp(col, _Wash.rgb, hatch * 0.35);
                half alpha = _Alpha * (1.0 + _Breath * sin(_Time.y * 2.8));
                // its ink line just inside the silhouette, two to three pixels wide whatever the zoom
                half fw = max(fwidth(nv), 1e-4);
                half ink = 1.0 - smoothstep(fw * 1.5, fw * 3.0, nv);
                col = lerp(col, _Ink.rgb, ink);
                alpha = lerp(alpha, 0.95, ink);
                return half4(col, alpha);
            }
            ENDHLSL
        }
    }
}
