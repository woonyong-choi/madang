// 템플릿 런타임과 테스트에 적용하는 Google JavaScript 스타일 가이드 규칙.
// runtime 폴더가 이 파일을 다시 내보내 두 폴더가 설정 하나를 공유한다.
const js = require('@eslint/js');
const stylistic = require('@stylistic/eslint-plugin');
const jsdoc = require('eslint-plugin-jsdoc');
const globals = require('globals');

// window.madang에 노출되는 함수. JSDoc이 필수다.
const RUNTIME_API = [
  'render',
  'setMode',
  'select',
  'clearSelection',
  'patchData',
  'renderMarkdown',
  'renderDocument',
  'setMarkdownRenderer',
  'setBridge',
  'sourceOf',
  'selectionInfo',
];

const style = {
  // 이어지는 줄은 스타일 가이드대로 +4 들여쓴다.
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
  // vendor/는 외부 라이브러리 원본을 그대로 둔다.
  {ignores: [
    'node_modules/',
    'test-results/',
    'playwright-report/',
    'vendor/',
  ]},
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
