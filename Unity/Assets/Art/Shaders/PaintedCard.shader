// A flat card carrying a piece of the painted art (window view, fire mouth, sieve, towel, scroll,
// chili string) inside the 3D cooking set: shown as painted, cut out along the picture's alpha.
// _Flicker > 0 makes it glow and waver a little (the fire mouth).
Shader "BianHe/PaintedCard"
{
    Properties
    {
        [NoScaleOffset] _MainTex ("Painting", 2D) = "white" {}
        _Tint ("Tint", Color) = (1, 1, 1, 1)
        _Flicker ("Flicker", Range(0, 1)) = 0
        _Cutoff ("Alpha Cutoff", Range(0, 1)) = 0.4
    }
    SubShader
    {
        Tags { "RenderType" = "TransparentCutout" "Queue" = "AlphaTest" "RenderPipeline" = "UniversalPipeline" }
        Pass
        {
            Name "Card"
            Tags { "LightMode" = "UniversalForward" }
            Cull Off
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            TEXTURE2D(_MainTex); SAMPLER(sampler_MainTex);
            CBUFFER_START(UnityPerMaterial)
                half4 _Tint;
                half _Flicker;
                half _Cutoff;
            CBUFFER_END
            struct A { float4 positionOS : POSITION; float2 uv : TEXCOORD0; };
            struct V { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; };
            V vert(A v) { V o; o.positionCS = TransformObjectToHClip(v.positionOS.xyz); o.uv = v.uv; return o; }
            half4 frag(V i) : SV_Target
            {
                half4 c = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv) * _Tint;
                clip(c.a - _Cutoff);
                float t = _Time.y;
                half glow = 1 + _Flicker * (0.12 + 0.08 * sin(t * 9 + i.uv.x * 6) + 0.05 * sin(t * 23));
                return half4(c.rgb * glow, 1);
            }
            ENDHLSL
        }
    }
}
