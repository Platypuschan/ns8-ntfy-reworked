module.exports = {
  publicPath: "./",
  // added to fix the build of https://github.com/NethServer/ns8-kickstart/pull/114
  transpileDependencies: ["axios"],
  configureWebpack: {
    optimization: {
      splitChunks: {
        minSize: 10000,
        maxSize: 250000,
      },
    },
  },
  css: {
    loaderOptions: {
      sass: {
        sassOptions: {
          silenceDeprecations: [
            "import",
            "global-builtin",
            "color-functions",
            "if-function",
            "legacy-js-api",
          ],
        },
      },
    },
  },
};
