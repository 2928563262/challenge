<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header-inner">
        <RouterLink class="brand-mark" to="/">
          <span class="brand-kicker">Shanghanlun KG</span>
          <strong>伤寒论知识图谱系统</strong>
        </RouterLink>

        <nav class="main-nav">
          <RouterLink to="/" class="nav-link">总览</RouterLink>
          <RouterLink to="/explore" class="nav-link">图谱浏览</RouterLink>
          <RouterLink to="/stats" class="nav-link">统计图表</RouterLink>
          <RouterLink to="/qa" class="nav-link">智能问答</RouterLink>
          <RouterLink to="/models" class="nav-link">模型工作台</RouterLink>
          <RouterLink to="/annotations" class="nav-link">候选复核</RouterLink>
        </nav>
      </div>
    </header>

    <RouterView />
  </div>
</template>
