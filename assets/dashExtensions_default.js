window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng, context) {
            options = {
                radius: 4,
                fillColor: "red",
                color: "#000",
                fillOpacity: 1,
                weight: 1
            };
            return L.circleMarker(latlng, options);
        }
    }
});