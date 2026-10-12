// Clear glass in the 水彩 look (the cola bottle): see-through where it faces the eye and fuller towards its edges,
// as a painter leaves glass mostly paper and lays its colour along the rims; lit in the same soft steps as
// WatercolorLit, with white streaks where it mirrors the light, and the same warm ink outline. Transparent: drawn
// after the opaque food, blended over whatever is behind it (the cola inside, the counter, the icon's empty
// background). Its alpha is blended as coverage, so a baked icon keeps the glass see-through. Its ink line is
// drawn inside its rim (_RimInk): it has no outline hull, whose far side would show through the clear glass.
Shader "BianHe/WatercolorGlass"
{
    Properties
    {
        _BaseColor ("Glass Color", Color) = (0.93, 0.93, 0.82, 1)
        _ShadeColor ("Shade Color", Color) = (0.72, 0.74, 0.62, 1)
        _Alpha ("Opacity Facing", Range(0, 1)) = 0.1
        _EdgeAlpha ("Opacity at the Edges", Range(0, 1)) = 0.7
        _Gloss ("Highlights", Range(0, 1)) = 1
        _RimInk ("Ink Line at the Rim", Range(0, 1)) = 1
        _OutlineColor ("Outline Color", Color) = (0.42, 0.27, 0.19, 1)
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "RenderPipeline" = "UniversalPipeline" "Queue" = "Transparent" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            half4 _BaseColor;
            half4 _ShadeColor;
            half _Alpha;
            half _EdgeAlpha;
            half _Gloss;
            half _RimInk;
            half4 _OutlineColor;
        CBUFFER_END
        float4 _ShadeLightDir;   // the painted light's direction (as in WatercolorLit), else the sun's
        ENDHLSL

        Pass
        {
            Name "GlassForward"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha, One OneMinusSrcAlpha
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; float3 smoothNormal : TEXCOORD3; };
            struct Varyings { float4 positionCS : SV_POSITION; float3 positionWS : TEXCOORD0; float3 normalWS : TEXCOORD1; };

            Varyings vert(Attributes v)
            {
                Varyings o;
                VertexPositionInputs p = GetVertexPositionInputs(v.positionOS.xyz);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.normalWS = TransformObjectToWorldNormal(dot(v.smoothNormal, v.smoothNormal) > 0.01 ? v.smoothNormal : v.normalOS);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float3 n = normalize(i.normalWS);
                float3 v = GetWorldSpaceNormalizeViewDir(i.positionWS);
                Light light = GetMainLight();
                float3 L = _ShadeLightDir.w > 0.5 ? normalize(_ShadeLightDir.xyz) : light.direction;
                half nv = saturate(abs(dot(n, v)));
                half edge = pow(1 - nv, 2.2);                          // 0 facing the eye .. 1 at the rims
                half lum = 0.25 + 0.75 * saturate(dot(n, L));
                half3 col = lerp(_ShadeColor.rgb, _BaseColor.rgb, smoothstep(0.3, 0.75, lum));
                half alpha = lerp(_Alpha, _EdgeAlpha, edge);
                // where it mirrors the light: on a bottle's round body a tall streak, white, and a fainter one
                // where it catches the room on the far side
                float3 h = normalize(L + v);
                half streak = smoothstep(0.94, 0.985, dot(n, h));
                half far = smoothstep(0.9, 0.97, dot(n, normalize(float3(-h.x, h.y, -h.z) + v))) * 0.45;
                half spec = saturate(streak + far) * _Gloss;
                col = lerp(col, half3(1.0, 0.99, 0.95), spec);
                alpha = max(alpha, spec * 0.9);
                // its ink line, drawn just inside its rim, about three pixels wide whatever the size (an outline
                // hull would show through the clear glass)
                half fw = max(fwidth(nv), 1e-4);
                half ink = (1 - smoothstep(fw * 2.0, fw * 3.5, nv)) * _RimInk;
                col = lerp(col, _OutlineColor.rgb, ink);
                alpha = max(alpha, ink);
                return half4(col, alpha);
            }
            ENDHLSL
        }
    }
}
