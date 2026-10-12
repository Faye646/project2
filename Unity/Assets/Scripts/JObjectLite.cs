using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace BianHe
{
    /// <summary>Small read-only view over a JSON object (cook_set.json markers): numbers, strings, vectors, lists.</summary>
    public class JObjectLite
    {
        readonly JToken t;
        /// <summary>Added to every point read with <see cref="Vec"/> on the root (the set's position in the scene).</summary>
        public Vector3 Offset;

        public JObjectLite(string json) : this(JToken.Parse(json)) { }
        JObjectLite(JToken token) { t = token; }

        public JObjectLite Obj(string key) => new(t[key]);
        public IEnumerable<JObjectLite> List(string key) => t[key].Select(x => new JObjectLite(x));
        public string Str(string key) => (string)t[key];
        public float Num(string key) => (float)t[key];

        public Vector3 Vec(string key)
        {
            var a = t[key];
            return new Vector3((float)a[0], (float)a[1], (float)a[2]) + Offset;
        }

        /// <summary>A list of points, each with <see cref="Offset"/> added as <see cref="Vec"/> does.</summary>
        public IEnumerable<Vector3> Vecs(string key) => t[key].Select(a => new Vector3((float)a[0], (float)a[1], (float)a[2]) + Offset);

        public bool Has(string key) => t[key] != null;
    }
}
