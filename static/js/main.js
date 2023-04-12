/**
 * funckia parsuje xml , vstupom je cesta k suboru ,vystupom je pole
 * @param file
 * @returns {{}}
 */
function parseModelDescription(file,zip) {
    var xmlDoc;
	if(zip !== true){
		if (typeof window.DOMParser != "undefined") {
			parser = new DOMParser();

			xmlhttp=new XMLHttpRequest();
			xmlhttp.open("GET",file,false);             //otvori xml subor
			if (xmlhttp.overrideMimeType){
				xmlhttp.overrideMimeType('text/xml');
			}
			xmlhttp.send();
			xmlDoc=xmlhttp.responseXML;
		} else {                                                    //IE
			xmlDoc = new ActiveXObject("Microsoft.XMLDOM");
			xmlDoc.async = false;
			xmlDoc.loadXML(file);
		}
	}else{
		parser = new DOMParser();
		xmlDoc = parser.parseFromString(file,"application/xml");
	}

    var resolver = xmlDoc.createNSResolver(xmlDoc.ownerDocument == null ? xmlDoc.documentElement : xmlDoc.ownerDocument.documentElement);
    var output = {};

    output.variables = parseVariables(resolver, xmlDoc);
    output.parameters = parseParameters(resolver, xmlDoc);
    output.arrays = findArrays(output.variables, output.parameters);
    output.modelName=parseFmiModelDescriptionAttribute(resolver, xmlDoc, 'modelName');
    output.guid=parseFmiModelDescriptionAttribute(resolver, xmlDoc, 'guid');
    output.description=parseFmiModelDescriptionAttribute(resolver, xmlDoc, 'description');
    output.generationTool=parseFmiModelDescriptionAttribute(resolver, xmlDoc, 'generationTool');
    output.generationDateAndTime=parseFmiModelDescriptionAttribute(resolver, xmlDoc, 'generationDateAndTime');

	//new
	output.startTime =parseDefaultExperiment(resolver,xmlDoc,'startTime');
	output.stopTime =parseDefaultExperiment(resolver,xmlDoc,'stopTime');
	output.tolerance =parseDefaultExperiment(resolver,xmlDoc,'tolerance');

    return output;
}

/**
 * funkcia rozparsuje v xml subore vsetky PREMENNE
 * @param resolver
 * @param xmlDoc
 * @returns {{}}
 */
const parseVariables = (resolver, xmlDoc) => {
    var variables = {};
    var variableIterator = xmlDoc.evaluate('//ScalarVariable[not(@causality="parameter")]', xmlDoc, resolver, XPathResult.UNORDERED_NODE_ITERATOR_TYPE, null);
    var node = variableIterator.iterateNext();

    while (node) {
        const name = node.getAttribute('name');
        variables[name] = {
            'name': node.getAttribute('name'),
            'reference': node.getAttribute('valueReference'),
            'description': node.getAttribute('description'),
            'causality': node.getAttribute('causality'),
            'variability': node.getAttribute('variability'),
            'initial': node.getAttribute('initial'),
            'canHandleMultipleSetPerTimeInstant': node.getAttribute('canHandleMultipleSetPerTimeInstant')
        };
        node = variableIterator.iterateNext();
    }

    return variables;
};

/**
 * funkcia rozparsuje v xml vsetky PARAMETRE
 * @param resolver
 * @param doc
 * @returns {{}}
 */
const parseParameters = (resolver, xmlDoc) => {
    var parameters = {};
    var parmIterator = xmlDoc.evaluate('//ScalarVariable[@causality="parameter"]',
	xmlDoc, resolver, XPathResult.UNORDERED_NODE_ITERATOR_TYPE, null);
    var node = parmIterator.iterateNext();

    while (node) {
        var name = node.getAttribute('name');
        parameters[name] = {
            'name': node.getAttribute('name'),
            'reference': node.getAttribute('valueReference'),
            'description': node.getAttribute('description'),
            'causality': node.getAttribute('causality'),
            'variability': node.getAttribute('variability'),
            'initial': node.getAttribute('initial'),
            'canHandleMultipleSetPerTimeInstant': node.getAttribute('canHandleMultipleSetPerTimeInstant')
        };
        node = parmIterator.iterateNext();
    }

    return parameters;
};

/**
 *
 * @param resolver
 * @param doc
 * @param attr
 * @returns {string}
 */
const parseFmiModelDescriptionAttribute = (resolver, doc, attr) => {
    const node = doc.evaluate('//fmiModelDescription', doc, resolver, XPathResult.ELEMENT_NODE, null).iterateNext();
    return node.getAttribute(attr);
};

/**
 *
 * @param resolver
 * @param doc
 * @param attr
 * @returns {string}
 */
const parseDefaultExperiment = (resolver, doc, attr) => {
    const node = doc.evaluate('//DefaultExperiment', doc, resolver, XPathResult.ELEMENT_NODE, null).iterateNext();
    return node.getAttribute(attr);
};

/**
 *
 * @param variables
 * @param parameters
 * @returns {{}}
 */
const findArrays = (variables, parameters) => {
    variables = Object.values(variables);
    parameters = Object.values(parameters);
    const providers = variables.concat(parameters).sort((a, b) => {
        return a.name.localeCompare(b.name);
    });
    const arrays = {};
    providers.forEach(provider => {
        if (/.*\[[0-9]*\]$/.test(provider.name) === false) {
            return null;
        }

        const regexed = provider.name.match(/(.*)\[([0-9]*)\]$/);
        const cname = regexed[1];
        const index = regexed[2];

        if (typeof arrays[cname] === 'undefined') {
            arrays[cname] = {
                cname,
                providers: {}
            };
        }

        arrays[cname].providers[provider.name] = {
            name: provider.name,
            index,
            reference: provider.reference
        };
    });
    return arrays;
};

function readSingleFile(e) {
    var file = e.target.files[0];
    console.log(file);
     if (!file) {
         return;
     }
     var reader = new FileReader();
     reader.onload = function(e) {
         var contents = e.target.result;
         displayContents(contents);
     };

    reader.readAsText(file);
}

function displayContents(contents) {
    var element = document.getElementById('file-content');
}


