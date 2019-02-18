import re, copy
from . import mistune

class MemriseRenderer(mistune.Renderer):
    def __init__(self, capture_images=None, *args, **kwargs):
        super(MemriseRenderer, self).__init__(*args, **kwargs)
        self.capture_images = capture_images
    
    def image(self, src, *args, **kwargs):
        if not self.capture_images is None:
            self.capture_images.append(src)
        return super(MemriseRenderer, self).image(src, *args, **kwargs)
    
    def embed(self, link, title, text):
        if link.startswith('javascript:'):
            link = ''
        if not title:
            return '<a href="%s" class="embed">%s</a>' % (link, text)
        title = mistune.escape(title, quote=True)
        return '<a href="%s" title="%s" class="embed">%s</a>' % (link, title, text)

class MemriseInlineGrammar(mistune.InlineGrammar):
    memrise_image = re.compile(r'^img:(([\s]+(https?:\/\/[^\s]+))|([^\s]+))')
    memrise_embed = re.compile(r'^embed:[\s]*(https?:\/\/[^\s]+)')
    text = re.compile(r'^[\s\S]+?(?=[\\<!\[_*`~]|https?://|img:|embed:| {2,}\n|$)')
    
class MemriseInlineLexer(mistune.InlineLexer):
    default_rules = copy.copy(mistune.InlineLexer.default_rules)
    default_rules.insert(0, 'memrise_image')
    default_rules.insert(1, 'memrise_embed')
    
    def __init__(self, renderer, rules=None, **kwargs):
        if rules is None:
            rules = MemriseInlineGrammar()

        super(MemriseInlineLexer, self).__init__(renderer, rules, **kwargs)
        
    def output_memrise_image(self, m):
        src = m.group(4) if m.group(4) else m.group(3)
        return self.renderer.image(src, "", "")
    
    def output_memrise_embed(self, m):
        href = m.group(1)
        return self.renderer.embed(href, "", href)

def Markdown(image_urls=None, **kwargs):
    return mistune.Markdown(renderer=MemriseRenderer(capture_images=image_urls), inline=MemriseInlineLexer, **kwargs)
    
def convert(text, image_urls=None, use_xhtml=True, **kwargs):
    return Markdown(image_urls, use_xhtml=use_xhtml, **kwargs)(text)
    
def convertAndReturnImages(text, **kwargs):
    image_urls = []
    output = convert(text, image_urls=image_urls, **kwargs)
    return output, image_urls
