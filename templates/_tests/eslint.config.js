// Google JavaScript Style Guide rules for the template runtime and its tests.
// The runtime folder re-exports this file so both folders share one config.
const js = require('@eslint/js');
const stylistic = require('@stylistic/eslint-plugin');
const jsdoc = require('eslint-plugin-jsdoc');
const globals = require('globals');

// Functions exposed on window.madang; their JSDoc is required.
const RUNTIME_API = [
  'render',
  'setMode',
  'select',
  'clearSelection',
  'patchData',
  'renderMarkdown',
  'setMarkdownRenderer',
  'setBridge',
  'sourceOf',
  'selectionInfo',
];

const style = {
  // Continuation lines get +4, as in the style guide.
  '@stylistic/indent': ['error', 2, {
    SwitchCase: 1,
    CallExpression: {arguments: 2},
    FunctionDeclaration: {body: 1, parameters: 2},
    FunctionExpression: {body: 1, parameters: 2},
    MemberExpression: 2,
    ignoredNodes: ['ConditionalExpression'],
  }],
  '@stylistic/quotes': ['error', 'single', {avoidEscape: true}],
  '@stylistic/semi': ['error', 'always'],
  '@stylistic/max-len': ['error', {
    code: 80,
    ignoreUrls: true,
    ignoreRegExpLiterals: true,
  }],
  '@stylistic/comma-dangle': ['error', 'always-multiline'],
  '@stylistic/object-curly-spacing': ['error', 'never'],
  '@stylistic/array-bracket-spacing': ['error', 'never'],
  '@stylistic/brace-style': ['error', '1tbs'],
  '@stylistic/arrow-parens': ['error', 'always'],
  '@stylistic/space-before-function-paren': ['error', {
    anonymous: 'never',
    named: 'never',
    asyncArrow: 'always',
  }],
  '@stylistic/keyword-spacing': 'error',
  '@stylistic/space-infix-ops': 'error',
  '@stylistic/comma-spacing': 'error',
  '@stylistic/key-spacing': 'error',
  '@stylistic/no-multi-spaces': 'error',
  '@stylistic/no-trailing-spaces': 'error',
  '@stylistic/eol-last': 'error',
  '@stylistic/no-tabs': 'error',
  'no-var': 'error',
  'prefer-const': 'error',
  'curly': ['error', 'multi-line'],
  'eqeqeq': 'error',
  'prefer-rest-params': 'error',
  'prefer-spread': 'error',
};

module.exports = [
  {ignores: ['node_modules/', 'test-results/', 'playwright-report/']},
  js.configs.recommended,
  jsdoc.configs['flat/recommended-error'],
  {
    plugins: {'@stylistic': stylistic},
    settings: {
      jsdoc: {
        mode: 'closure',
        tagNamePreference: {returns: 'return'},
        preferredTypes: {object: 'Object'},
      },
    },
    rules: {
      ...style,
      'jsdoc/require-jsdoc': 'off',
      'jsdoc/require-param-description': 'off',
      'jsdoc/require-returns-description': 'off',
      'jsdoc/tag-lines': ['error', 'any', {startLines: 1}],
      'jsdoc/reject-any-type': 'off',
    },
  },
  {
    files: ['**/madang.js'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'script',
      globals: globals.browser,
    },
    rules: {
      'jsdoc/require-jsdoc': ['error', {
        require: {FunctionDeclaration: false},
        contexts: [
          `FunctionDeclaration[id.name=/^(${RUNTIME_API.join('|')})$/]`,
        ],
      }],
    },
  },
  {
    files: ['**/*.js'],
    ignores: ['**/madang.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {...globals.node, ...globals.browser},
    },
    rules: {
      'jsdoc/require-jsdoc': ['error', {publicOnly: {cjs: true}}],
    },
  },
];
